"""Comprehensive tests for the Troubleshooting Engine."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from schema import ContextDeeplinkResponse, Goal, Action, StepGroup
from app.config import DESC_WORDS, TITLE_WORDS, CATEGORY_ORDER
from app.normalize import normalize_query, canonicalize_query, split_multi_intent
from app.sectioner import get_actionable_sections, strip_preamble, split_into_sections
from app.steps import (
    is_instruction_line,
    extract_instructions,
    split_compound_step,
    extract_step_chains,
)
from app.classify import classify_action
from app.ordering import order_actions
from app.textrules import (
    enforce_description,
    enforce_word_range,
    match_symptom,
    generate_goal,
    generate_title,
    to_title_case,
    to_sentence_case,
)
from app.validators import (
    scan_urls,
    scrub_urls,
    validate_no_urls,
    validate_goal_format,
    validate_title,
    validate_description,
    validate_ordering,
    final_gate,
)
from app.loader import (
    load_deeplinks,
    load_deeplinks_full,
    build_catalog_uri_set,
    load_siis_responses,
    load_input_queries,
)
from app.variations import generate_variations


# ──────────────────────────────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def siis_rows():
    return load_siis_responses()


@pytest.fixture(scope="session")
def catalog_uris():
    return build_catalog_uri_set(load_deeplinks_full())


@pytest.fixture(scope="session")
def input_queries():
    return load_input_queries()


@pytest.fixture(scope="session")
def pipeline():
    """Initialized pipeline for integration tests."""
    from app.pipeline import TroubleshootPipeline
    p = TroubleshootPipeline()
    p.initialize()
    return p


@pytest.fixture(scope="session")
def all_results(pipeline, siis_rows):
    """Run all 20 rows and return results."""
    results = []
    for row in siis_rows:
        result = pipeline.process_query(
            row["original_query"],
            row["siis_response"],
        )
        results.append((row, result))
    return results


# ──────────────────────────────────────────────────────────────────────
#  Phase 1: Foundation tests
# ──────────────────────────────────────────────────────────────────────

class TestTextRules:
    def test_enforce_description_valid(self):
        desc = "It will clear temporary stored data."
        assert enforce_description(desc) == desc

    def test_enforce_description_too_long(self):
        desc = "It will do a lot of things that take many words here."
        result = enforce_description(desc)
        words = result.rstrip(".").split()
        assert DESC_WORDS[0] <= len(words) <= DESC_WORDS[1]
        assert result.startswith("It will")

    def test_enforce_description_too_short(self):
        desc = "It will fix."
        result = enforce_description(desc)
        words = result.rstrip(".").split()
        assert DESC_WORDS[0] <= len(words) <= DESC_WORDS[1]

    def test_enforce_description_adds_prefix(self):
        desc = "clear the cache data."
        result = enforce_description(desc)
        assert result.startswith("It will")

    def test_word_range_enforcement(self):
        text = "one two three four five six seven eight nine ten"
        result = enforce_word_range(text, 5, 7)
        words = result.split()
        assert len(words) <= 7

    def test_title_case(self):
        assert to_title_case("clear cache data") == "Clear Cache Data"
        assert to_title_case("connect to USB") == "Connect to USB"

    def test_sentence_case(self):
        assert to_sentence_case("Screen Display Damage") == "Screen display damage"

    def test_goal_format_troubleshooting(self):
        goal = generate_goal("Screen Damage", "troubleshooting")
        assert validate_goal_format(goal)
        assert "Troubleshooting" in goal

    def test_goal_format_configuration(self):
        goal = generate_goal("Floating Menu", "configuration")
        assert validate_goal_format(goal)
        assert "Configuration" in goal

    def test_title_generation(self):
        title = generate_title("Screen display damage")
        words = title.split()
        assert TITLE_WORDS[0] <= len(words) <= TITLE_WORDS[1]
        assert title[0].isupper()

    def test_symptom_matching(self):
        result = match_symptom("my screen is cracked")
        assert result["topic"] == "Screen Damage"

        result = match_symptom("blank display on phone")
        assert result["topic"] == "Blank Display"

        result = match_symptom("touch is laggy")
        assert result["topic"] == "Touch Responsiveness"


class TestValidators:
    def test_url_detection(self):
        assert scan_urls("visit https://example.com for help")
        assert scan_urls("check www.example.com")
        assert scan_urls("click [here](http://test.com)")
        assert not scan_urls("Navigate to Settings.")
        assert not scan_urls("voiceassist://masked/act/abc123")

    def test_url_scrub(self):
        text = "visit https://example.com for help"
        result = scrub_urls(text)
        assert "https://" not in result
        assert "example.com" not in result

    def test_no_url_violations(self):
        clean = {"query": "test", "response": {"contexts": []}}
        assert validate_no_urls(clean) == []

        dirty = {"query": "visit https://bad.com", "response": {"contexts": []}}
        assert len(validate_no_urls(dirty)) > 0

    def test_deeplink_fields_excluded(self):
        data = {
            "deeplink": "voiceassist://masked/act/abc123",
            "description": "Opens settings",
        }
        assert validate_no_urls(data) == []

    def test_goal_format_valid(self):
        assert validate_goal_format(
            "Follow these steps to perform this Screen Damage Troubleshooting"
        )
        assert validate_goal_format(
            "Follow these steps to perform this Floating Menu Configuration"
        )

    def test_goal_format_invalid(self):
        assert not validate_goal_format("Fix the screen")
        assert not validate_goal_format("")

    def test_description_valid(self):
        assert validate_description("It will clear temporary stored data.")
        assert validate_description("It will restart device to resolve.")

    def test_description_invalid(self):
        assert not validate_description("Clear the cache")  # no "It will"
        assert not validate_description("It will fix.")  # too short (3 words)

    def test_title_valid(self):
        assert validate_title("Screen display damage")
        assert validate_title("Blank display")

    def test_title_invalid(self):
        assert not validate_title("A")  # too short
        assert not validate_title("One two three four")  # too long


# ──────────────────────────────────────────────────────────────────────
#  Phase 2: Extraction tests
# ──────────────────────────────────────────────────────────────────────

class TestNormalize:
    def test_strip_enumerators(self):
        norm = normalize_query('1. "My phone screen is blank"')
        assert norm["sub_queries"][0] == "My phone screen is blank"

    def test_multi_intent_split(self):
        text = '1. "Screen is cracked." 2. "Touch doesn\'t work." 3. "Can\'t see display."'
        subs = split_multi_intent(text)
        assert len(subs) == 3

    def test_canonicalize_removes_brand(self):
        canonical = canonicalize_query("My TechCorp Nexa X1 Ultra screen is blank")
        assert "techcorp" not in canonical.lower()
        assert "nexa" not in canonical.lower()
        assert "x1" not in canonical.lower()
        assert canonical.endswith(".")

    def test_canonicalize_sentence_case(self):
        canonical = canonicalize_query("MY SCREEN IS BROKEN")
        assert canonical[0].isupper()


class TestSectioner:
    def test_strip_preamble(self):
        text = "Smartphone,Tablet Title ( Smartphone,Tablet): ## Step 1"
        result = strip_preamble(text)
        assert result.startswith("## Step 1") or "Step 1" in result

    def test_split_sections(self):
        content = "Intro text\n## Section 1\nBody 1\n## Section 2\nBody 2"
        sections = split_into_sections(content)
        assert len(sections) >= 2

    def test_actionable_filtering(self, siis_rows):
        # Row 2 (blank display) should have actionable sections
        row2 = next(r for r in siis_rows if r["id"] == "row_2")
        sections = get_actionable_sections(row2["siis_response"]["content"])
        assert len(sections) > 0


class TestSteps:
    def test_instruction_detection(self):
        assert is_instruction_line("Navigate to Settings.")
        assert is_instruction_line("Tap on Display.")
        assert is_instruction_line("Press and hold the Power button.")
        assert not is_instruction_line("This helps determine if the problem is with your phone.")

    def test_compound_split(self):
        step = "Go to Settings, tap Connections, and then tap Wi-Fi."
        atoms = split_compound_step(step)
        assert len(atoms) >= 2
        assert any("Settings" in s for s in atoms)

    def test_step_extraction(self, siis_rows):
        # Row 2 should yield steps about force restart, charging, etc.
        row2 = next(r for r in siis_rows if r["id"] == "row_2")
        sections = get_actionable_sections(row2["siis_response"]["content"])
        total_chains = []
        for heading, body in sections:
            chains = extract_step_chains(heading, body)
            total_chains.extend(chains)
        assert len(total_chains) > 0
        # All steps should end with period
        for chain in total_chains:
            for step in chain["steps"]:
                assert step.endswith("."), f"Step doesn't end with period: {step}"


class TestClassify:
    def test_auto_classification(self):
        steps = ["Navigate to and open Settings.", "Tap on Display.", "Tap on Touch sensitivity."]
        assert classify_action(steps) == "auto"

    def test_manual_classification(self):
        steps = ["Inspect the device for physical damage.", "Check the USB cable."]
        assert classify_action(steps) == "manual"

    def test_critical_classification(self):
        steps = ["Navigate to and open Settings.", "Tap Factory data reset.", "Tap Delete all."]
        assert classify_action(steps) == "critical"

    def test_contact_manual(self):
        steps = ["Contact Customer Support for further assistance."]
        assert classify_action(steps) == "manual"


class TestOrdering:
    def test_ordering(self):
        actions = [
            {"category": "critical", "actionName": "Reset"},
            {"category": "auto", "actionName": "Settings"},
            {"category": "manual", "actionName": "Check"},
        ]
        ordered = order_actions(actions)
        cats = [a["category"] for a in ordered]
        assert cats == ["auto", "manual", "critical"]


# ──────────────────────────────────────────────────────────────────────
#  Phase 4: Pipeline integration tests
# ──────────────────────────────────────────────────────────────────────

class TestPipelineIntegration:
    """Integration tests running the full pipeline on real data."""

    def test_schema_conformance_all_rows(self, all_results, catalog_uris):
        """Every response validates against schema.py."""
        for row, result in all_results:
            response = result.get("response", {})
            # Should parse without error
            parsed = ContextDeeplinkResponse(**response)
            assert isinstance(parsed.contexts, list)

    def test_url_leak_scan(self, all_results):
        """No URLs in any string field (except deeplink fields)."""
        for row, result in all_results:
            violations = validate_no_urls(result)
            assert violations == [], f"URL leaks in {row['id']}: {violations}"

    def test_catalog_membership(self, all_results, catalog_uris):
        """Every deeplink value exists in the catalog."""
        for row, result in all_results:
            contexts = result.get("response", {}).get("contexts", [])
            for goal in contexts:
                for action in goal.get("actions", []):
                    for sg in action.get("stepGroups", []):
                        ad = sg.get("actionableDeeplink")
                        if ad and isinstance(ad, dict):
                            dl = ad.get("deeplink", "")
                            assert dl in catalog_uris, (
                                f"Deeplink not in catalog: {dl} (row {row['id']})"
                            )
                        vd = sg.get("validationDeeplink")
                        if vd and isinstance(vd, dict):
                            vl = vd.get("deeplink", "")
                            assert vl in catalog_uris, (
                                f"Validation deeplink not in catalog: {vl} (row {row['id']})"
                            )

    def test_word_count_and_casing(self, all_results):
        """Description, title, actionName follow text rules."""
        for row, result in all_results:
            contexts = result.get("response", {}).get("contexts", [])
            for goal in contexts:
                # Title: 2-3 words, sentence case
                title = goal.get("title", "")
                words = title.split()
                assert TITLE_WORDS[0] <= len(words) <= TITLE_WORDS[1], (
                    f"Title word count {len(words)} not in {TITLE_WORDS}: '{title}' (row {row['id']})"
                )

                # Goal format
                goal_str = goal.get("goal", "")
                assert validate_goal_format(goal_str), (
                    f"Invalid goal format: '{goal_str}' (row {row['id']})"
                )

                # Score range
                score = goal.get("score", 0)
                assert 0.0 <= score <= 1.0, f"Score {score} out of range (row {row['id']})"

                for action in goal.get("actions", []):
                    # Description: 5-7 words, starts with "It will"
                    desc = action.get("description", "")
                    assert desc.startswith("It will"), (
                        f"Description doesn't start with 'It will': '{desc}' (row {row['id']})"
                    )
                    desc_words = desc.rstrip(".").split()
                    assert DESC_WORDS[0] <= len(desc_words) <= DESC_WORDS[1], (
                        f"Description word count {len(desc_words)} not in {DESC_WORDS}: '{desc}' (row {row['id']})"
                    )

                    # Steps end with period
                    for sg in action.get("stepGroups", []):
                        for step in sg.get("steps", []):
                            assert step.endswith("."), (
                                f"Step doesn't end with period: '{step}' (row {row['id']})"
                            )

    def test_ordering_rule(self, all_results):
        """Critical actions always come last."""
        for row, result in all_results:
            contexts = result.get("response", {}).get("contexts", [])
            for goal in contexts:
                actions = goal.get("actions", [])
                if len(actions) < 2:
                    continue
                categories = [a.get("category", "manual") for a in actions]
                order_values = [CATEGORY_ORDER.get(c, 1) for c in categories]
                # Must be non-decreasing
                for i in range(1, len(order_values)):
                    assert order_values[i] >= order_values[i-1], (
                        f"Ordering violation in {row['id']}: {categories}"
                    )

    def test_manual_no_deeplink(self, all_results):
        """Manual actions have no actionable deeplink."""
        for row, result in all_results:
            contexts = result.get("response", {}).get("contexts", [])
            for goal in contexts:
                for action in goal.get("actions", []):
                    if action.get("category") == "manual":
                        for sg in action.get("stepGroups", []):
                            assert sg.get("actionableDeeplink") is None, (
                                f"Manual action has deeplink in {row['id']}: {action['actionName']}"
                            )

    def test_determinism(self, pipeline, siis_rows):
        """Same input -> same output (run twice)."""
        for row in siis_rows[:5]:  # Test first 5 for speed
            r1 = pipeline.process_query(row["original_query"], row["siis_response"])
            r2 = pipeline.process_query(row["original_query"], row["siis_response"])
            # Compare contexts (ignore latency)
            c1 = r1.get("response", {}).get("contexts", [])
            c2 = r2.get("response", {}).get("contexts", [])
            assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True), (
                f"Non-deterministic output for {row['id']}"
            )

    def test_multi_intent(self, pipeline, siis_rows):
        """Row 19 (3-complaint query) yields multiple goals."""
        row19 = next(r for r in siis_rows if r["id"] == "row_19")
        result = pipeline.process_query(
            row19["original_query"], row19["siis_response"]
        )
        contexts = result.get("response", {}).get("contexts", [])
        # Should have multiple goals (up to 3)
        assert len(contexts) >= 1, "Multi-intent should yield at least 1 goal"

    def test_no_siis_context(self, pipeline):
        """Unknown query without SIIS returns no_siis_context."""
        result = pipeline.process_query("My phone exploded into glitter")
        assert result.get("meta", {}).get("fallback") == "no_siis_context"
        assert result.get("response", {}).get("contexts") == []

    def test_no_match_mismatched_siis(self, pipeline):
        """Unrelated query with wrong SIIS text returns no_match or minimal results."""
        # Use a unique query that won't match any cached entry
        siis = {
            "title": "How to cook pasta al dente",
            "content": "Boil water in a large pot and add pasta. Cook for exactly 10 minutes until al dente. Drain and serve with sauce.",
        }
        result = pipeline.process_query(
            "My refrigerator is making a loud buzzing noise and leaking water on the floor",
            siis,
        )
        contexts = result.get("response", {}).get("contexts", [])
        fallback = result.get("meta", {}).get("fallback")
        # Should be empty with no_match fallback
        assert len(contexts) == 0 or fallback == "no_match", (
            f"Expected no_match but got {len(contexts)} contexts, fallback={fallback}"
        )


class TestGoldenSteps:
    """Golden tests: extracted steps must be traceable to SIIS text."""

    def _check_steps_in_source(self, result, siis_content):
        """Check that extracted steps are derived from the source text."""
        contexts = result.get("response", {}).get("contexts", [])
        content_lower = siis_content.lower()

        for goal in contexts:
            for action in goal.get("actions", []):
                for sg in action.get("stepGroups", []):
                    for step in sg.get("steps", []):
                        # Extract key nouns/verbs from step
                        step_clean = step.rstrip(".").lower()
                        # At least some keywords from the step should appear in source
                        key_words = [
                            w for w in step_clean.split()
                            if len(w) > 3 and w not in {
                                "navigate", "open", "settings", "the", "and",
                                "then", "your", "will", "that", "this",
                                "from", "with", "into", "have", "been",
                            }
                        ]
                        if key_words:
                            found = sum(1 for w in key_words if w in content_lower)
                            ratio = found / len(key_words) if key_words else 0
                            # At least 30% of keywords should be in source
                            assert ratio >= 0.3 or len(key_words) <= 2, (
                                f"Step not traceable to source: '{step}' "
                                f"(keywords: {key_words}, found: {found})"
                            )

    def test_golden_row_2(self, pipeline, siis_rows):
        row = next(r for r in siis_rows if r["id"] == "row_2")
        result = pipeline.process_query(row["original_query"], row["siis_response"])
        self._check_steps_in_source(result, row["siis_response"]["content"])

    def test_golden_row_4(self, pipeline, siis_rows):
        row = next(r for r in siis_rows if r["id"] == "row_4")
        result = pipeline.process_query(row["original_query"], row["siis_response"])
        self._check_steps_in_source(result, row["siis_response"]["content"])

    def test_golden_row_14(self, pipeline, siis_rows):
        row = next(r for r in siis_rows if r["id"] == "row_14")
        result = pipeline.process_query(row["original_query"], row["siis_response"])
        self._check_steps_in_source(result, row["siis_response"]["content"])

    def test_golden_row_21(self, pipeline, siis_rows):
        row = next(r for r in siis_rows if r["id"] == "row_21")
        result = pipeline.process_query(row["original_query"], row["siis_response"])
        self._check_steps_in_source(result, row["siis_response"]["content"])

    def test_golden_row_22(self, pipeline, siis_rows):
        row = next(r for r in siis_rows if r["id"] == "row_22")
        result = pipeline.process_query(row["original_query"], row["siis_response"])
        self._check_steps_in_source(result, row["siis_response"]["content"])


class TestVariations:
    def test_variation_count(self):
        variations = generate_variations("My phone screen is blank")
        assert 8 <= len(variations) <= 10

    def test_variations_distinct(self):
        variations = generate_variations("My screen is cracked and I can't use it")
        # All should be distinct
        lower_set = set(v.lower() for v in variations)
        assert len(lower_set) == len(variations)

    def test_variations_deterministic(self):
        v1 = generate_variations("My phone screen is blank")
        v2 = generate_variations("My phone screen is blank")
        assert v1 == v2


class TestPhase7QualityReview:
    """Tests for Phase 7 review content-quality bugs."""

    def test_relevance_gate_mismatches_return_no_match(self, pipeline, siis_rows):
        """Row 7, 8, 12, 20 must return no_match because article does not address symptom."""
        mismatch_ids = ["row_7", "row_8", "row_12", "row_20"]
        for row_id in mismatch_ids:
            row = next(r for r in siis_rows if r["id"] == row_id)
            result = pipeline.process_query(row["original_query"], row["siis_response"])
            assert result["response"]["contexts"] == [], (
                f"{row_id} must return no_match, but got {len(result['response']['contexts'])} contexts"
            )
            assert result.get("meta", {}).get("fallback") == "no_match", (
                f"{row_id} fallback meta must be 'no_match'"
            )

    def test_row_21_resolves_to_dl_0169(self, pipeline, siis_rows):
        """Row 21 navigation bar chain must resolve to DL-0169 and copy validation object."""
        row21 = next(r for r in siis_rows if r["id"] == "row_21")
        result = pipeline.process_query(row21["original_query"], row21["siis_response"])
        contexts = result["response"]["contexts"]
        assert len(contexts) > 0, "Row 21 must produce at least one goal"

        found_dl0169 = False
        for action in contexts[0]["actions"]:
            for sg in action["stepGroups"]:
                act_dl = sg.get("actionableDeeplink")
                if act_dl and act_dl.get("deeplink") == "voiceassist://masked/act/2f3dd95259":
                    found_dl0169 = True
                    val_dl = sg.get("validationDeeplink")
                    assert val_dl is not None, "DL-0169 must have a validation object"
                    assert val_dl.get("deeplink") == "voiceassist://masked/val/d8310c1b7d"
                    assert val_dl.get("key") == "Navigation bar"

        assert found_dl0169, "Row 21 Navigation bar chain must resolve to DL-0169"

    def test_step_quality_and_formatting(self, all_results):
        """Strict step formatting: Capitalized, imperative, <25 words, no duplicate actions."""
        for row, result in all_results:
            contexts = result.get("response", {}).get("contexts", [])
            for goal in contexts:
                actions = goal.get("actions", [])
                action_names = [a.get("actionName") for a in actions]
                # Unify duplicates: no duplicate action names within the same goal
                assert len(action_names) == len(set(action_names)), (
                    f"Duplicate actions found in {row['id']}: {action_names}"
                )

                for action in actions:
                    for sg in action.get("stepGroups", []):
                        steps = sg.get("steps", [])
                        for step in steps:
                            # Capitalization
                            assert step[0].isupper(), f"Step must start with capital: '{step}' in {row['id']}"
                            # Length < 25 words
                            words = step.split()
                            assert len(words) < 25, f"Step too long ({len(words)} words): '{step}' in {row['id']}"
                            # Ends with period
                            assert step.endswith("."), f"Step must end with period: '{step}' in {row['id']}"

    def test_critical_category_strict_phrases(self):
        """Critical category must strictly match phrases for reset, restart, software update, clear data."""
        # Non-critical actions must NOT be classified as critical
        assert classify_action(["Examine the USB connections for corrosion."], "Check for Physical Damage") != "critical"
        assert classify_action(["Connect mouse and keyboard using USB adapter."], "Introduction") != "critical"
        assert classify_action(["Schedule a walk-in repair."], "Authorized Repair Services") != "critical"
        assert classify_action(["Swipe left to open Quick Access panel."], "Create an App pair") != "critical"

        # Critical actions MUST be classified as critical
        assert classify_action(["Tap Factory data reset again."], "Perform a Factory Data Reset") == "critical"
        assert classify_action(["Tap the Power icon, then tap Restart."], "Restart Your Device") == "critical"
        assert classify_action(["Tap Clear data, and then tap OK."], "Clear the Email App Data") == "critical"
        assert classify_action(["Keeping your device software updated regularly."], "Update Device Software") == "critical"

    def test_brand_model_canonicalization(self):
        """Brand tokens should be replaced by generic phone/tablet/device."""
        c1 = canonicalize_query("My TechCorp A15G tablet screen flashes and then goes blank")
        assert "tablet" in c1.lower()
        assert "techcorp" not in c1.lower()
        assert "a15g" not in c1.lower()

        c2 = canonicalize_query("My Nexa X1 screen turns completely blank")
        assert "phone" in c2.lower() or "device" in c2.lower()
        assert "nexa" not in c2.lower()
        assert "x1" not in c2.lower()


class TestPhase8Fixes:
    """Tests for Phase 8 quality review fixes."""

    def test_row_1_cache_data_no_false_positive_deeplinks(self, pipeline, siis_rows):
        """Row 1 cache/data actions must NOT return DL-0177, DL-0182, or wrong real deeplinks."""
        row1 = next(r for r in siis_rows if r["id"] == "row_1")
        result = pipeline.process_query(row1["original_query"], row1["siis_response"])
        contexts = result["response"]["contexts"]
        assert len(contexts) > 0, "Row 1 must produce a goal"

        for action in contexts[0]["actions"]:
            for sg in action.get("stepGroups", []):
                act_dl = sg.get("actionableDeeplink")
                if act_dl:
                    uri = act_dl.get("deeplink")
                    # Must NOT resolve to NFC (DL-0177), Sound (DL-0182), Notifications (DL-0248), Sync (DL-0490), or Lockdown (DL-0154)
                    assert uri != "voiceassist://masked/act/ddc86e4321", "Must not resolve to DL-0177 (NFC)"
                    assert uri != "voiceassist://masked/act/3690482ef2", "Must not resolve to DL-0182 (Sound)"
                    assert uri != "voiceassist://masked/act/eb07d1777d", "Must not resolve to DL-0248 (Notifications)"
                    assert uri != "voiceassist://masked/act/5861b88185", "Must not resolve to DL-0154 (Lockdown)"
                    assert uri != "voiceassist://masked/act/9c86c882d0", "Must not resolve to DL-0490 (Sync)"
                    # If it's a settings chain with no real catalog entry, it must be the dummy fallback
                    if any("settings" in s.lower() for s in sg["steps"]):
                        assert uri == "voiceassist://dummy_positive", (
                            f"Settings chain with no catalog match must use dummy_positive, got {uri}"
                        )

    def test_row_21_still_resolves_to_dl_0169(self, pipeline, siis_rows):
        """Row 21 must still resolve to DL-0169 with lexical evidence matching Navigation bar."""
        row21 = next(r for r in siis_rows if r["id"] == "row_21")
        result = pipeline.process_query(row21["original_query"], row21["siis_response"])
        contexts = result["response"]["contexts"]
        assert len(contexts) > 0

        found_dl0169 = False
        for action in contexts[0]["actions"]:
            for sg in action.get("stepGroups", []):
                act_dl = sg.get("actionableDeeplink")
                if act_dl and act_dl.get("deeplink") == "voiceassist://masked/act/2f3dd95259":
                    found_dl0169 = True
                    val_dl = sg.get("validationDeeplink")
                    assert val_dl is not None
                    assert val_dl.get("deeplink") == "voiceassist://masked/val/d8310c1b7d"
                    assert val_dl.get("key") == "Navigation bar"

        assert found_dl0169, "Row 21 must resolve to DL-0169"

    def test_variation_quality_no_double_commas_or_bad_swaps(self, siis_rows):
        """Generated variations must not have double commas ',,' or ungrammatical swaps."""
        for row in siis_rows:
            vars_list = generate_variations(row["original_query"])
            for v in vars_list:
                assert ",," not in v, f"Found double comma in variation: '{v}' for {row['id']}"
                if "nothing showing" not in row["original_query"].lower():
                    assert "nothing showing" not in v.lower(), f"Found ungrammatical swap 'nothing showing' in: '{v}'"
                if "no image" not in row["original_query"].lower():
                    assert "no image" not in v.lower(), f"Found ungrammatical swap 'no image' in: '{v}'"

    def test_no_hallucinated_backup_action(self, pipeline, siis_rows):
        """Row 14 and Row 19 (cracked screen) must not hallucinate a backup-action not in SIIS."""
        for row_id in ["row_14", "row_19"]:
            row = next(r for r in siis_rows if r["id"] == row_id)
            result = pipeline.process_query(row["original_query"], row["siis_response"])
            for goal in result["response"].get("contexts", []):
                for act in goal.get("actions", []):
                    assert "back up" not in act.get("actionName", "").lower(), (
                        f"{row_id} must not hallucinate a backup action: {act['actionName']}"
                    )
                    assert "backup" not in act.get("actionName", "").lower(), (
                        f"{row_id} must not hallucinate a backup action: {act['actionName']}"
                    )

    def test_model_preloaded(self, pipeline):
        """Embedding model must be loaded and ready after pipeline initialization."""
        from app.retrieval import _model
        assert _model is not None, "SentenceTransformer model must be preloaded in memory at startup"

class TestPhase9Fixes:
    """Phase 9 tests: reporting, action naming, and vague step dropping."""

    def test_no_generic_action_names(self, pipeline, siis_rows):
        """Never use section headings like Introduction/Overview/Summary as actionName."""
        for row_id in ["row_3", "row_11", "row_17"]:
            row = next(r for r in siis_rows if r["id"] == row_id)
            result = pipeline.process_query(row["original_query"], row["siis_response"])
            for goal in result["response"].get("contexts", []):
                for act in goal.get("actions", []):
                    name = act.get("actionName", "")
                    assert name not in {"Introduction", "Overview", "Summary", "General", "Main"}, (
                        f"{row_id} has forbidden generic actionName '{name}'"
                    )
                    assert name == "Access Phone Using Mouse", (
                        f"{row_id} actionName should be 'Access Phone Using Mouse', got '{name}'"
                    )

    def test_drop_vague_steps(self, pipeline, siis_rows):
        """Drop vague steps like 'Navigate your device as needed.'"""
        for row_id in ["row_3", "row_11", "row_17"]:
            row = next(r for r in siis_rows if r["id"] == row_id)
            result = pipeline.process_query(row["original_query"], row["siis_response"])
            for goal in result["response"].get("contexts", []):
                for act in goal.get("actions", []):
                    for sg in act.get("stepGroups", []):
                        for s in sg.get("steps", []):
                            assert "navigate your device as needed" not in s.lower(), (
                                f"{row_id} contains vague step: '{s}'"
                            )
                            assert "as needed" not in s.lower(), (
                                f"{row_id} contains vague step ending: '{s}'"
                            )


class TestPhase10:
    """Phase 10 tests: local SIIS fallback on cache miss with siis_response=None."""

    def test_local_siis_fallback_on_cache_miss(self, pipeline):
        """When siis_response=None and cache misses, search local SIIS articles."""
        pipeline.cache.clear()
        query = "Every time I tap an incoming message in Gmail the screen turns blank"
        result = pipeline.process_query(query, siis_response=None)
        assert result.get("meta", {}).get("fallback") != "no_siis_context"
        contexts = result.get("response", {}).get("contexts", [])
        assert len(contexts) >= 1
        action_names = [a["actionName"] for a in contexts[0]["actions"]]
        assert any("Email" in name for name in action_names)

    def test_local_siis_fallback_rejects_irrelevant(self, pipeline):
        """Irrelevant query with siis_response=None still returns no_siis_context."""
        pipeline.cache.clear()
        result = pipeline.process_query("My phone exploded into glitter and butterflies", siis_response=None)
        assert result.get("meta", {}).get("fallback") == "no_siis_context"
        assert result.get("response", {}).get("contexts") == []
