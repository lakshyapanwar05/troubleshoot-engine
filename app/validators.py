"""Final gate validators — URL scrub, schema check, catalog membership, rule enforcement.

Every response passes final_gate() before returning to the API.
On failure, apply deterministic auto-fix; if unfixable, drop the action.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional, Set

from pydantic import ValidationError

from schema import (
    Action,
    ContextDeeplinkResponse,
    Deeplink,
    Goal,
    StepGroup,
    ValidationDeepLink,
    actionCategory,
)
from app.config import (
    CATEGORY_ORDER,
    DESC_WORDS,
    TITLE_WORDS,
    MAX_ACTIONS_PER_GOAL,
)
from app.textrules import (
    enforce_description,
    to_sentence_case,
    to_title_case,
)

logger = logging.getLogger(__name__)

# ── URL / domain detection regex ──────────────────────────────────────
# Matches http://, https://, www., markdown links [x](y), bare domains
_URL_PATTERN = re.compile(
    r"(?:"
    r"https?://"             # http:// or https://
    r"|www\."                # www.
    r"|\[.*?\]\(.*?\)"       # markdown links [text](url)
    r"|(?<!\w)[a-zA-Z0-9-]+\.(?:com|org|net|io|co|edu|gov|info|biz)\b"  # bare domains
    r")",
    re.IGNORECASE,
)

# Deeplink URI prefix — these are allowed
_DEEPLINK_PREFIX = "voiceassist://"

# Goal regex
_GOAL_RE = re.compile(
    r"^Follow these steps to perform this [A-Z].+ (Troubleshooting|Configuration)$"
)


def scan_urls(text: str) -> list[str]:
    """Find URL-like strings in text (excluding deeplink fields)."""
    return _URL_PATTERN.findall(text)


def scrub_urls(text: str) -> str:
    """Remove URL-like substrings from text, excluding voiceassist:// deeplinks."""
    # First protect deeplinks
    deeplink_placeholder = "___DEEPLINK_PLACEHOLDER___"
    protected = text
    deeplink_matches = list(re.finditer(r"voiceassist://\S+", text))
    for i, m in enumerate(reversed(deeplink_matches)):
        protected = protected[:m.start()] + f"{deeplink_placeholder}{i}" + protected[m.end():]

    # Scrub URLs
    protected = _URL_PATTERN.sub("", protected)

    # Also scrub email-like patterns
    protected = re.sub(r"\S+@\S+\.\S+", "", protected)

    # Restore deeplinks
    for i, m in enumerate(reversed(deeplink_matches)):
        protected = protected.replace(f"{deeplink_placeholder}{i}", m.group())

    # Clean up extra whitespace
    protected = re.sub(r"\s{2,}", " ", protected).strip()
    return protected


def validate_no_urls(obj: Any, path: str = "", exclude_deeplink_fields: bool = True) -> list[str]:
    """Recursively scan all string values in a dict/list for URL leaks.

    Returns a list of (path, matched_url) strings for any violations.
    """
    violations = []

    # Fields that are allowed to contain deeplink URIs
    deeplink_fields = {"deeplink"} if exclude_deeplink_fields else set()

    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            if k in deeplink_fields:
                continue  # skip deeplink fields
            violations.extend(validate_no_urls(v, child_path, exclude_deeplink_fields))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(validate_no_urls(item, f"{path}[{i}]", exclude_deeplink_fields))
    elif isinstance(obj, str):
        # Skip if the string itself IS a deeplink
        if obj.startswith(_DEEPLINK_PREFIX):
            return violations
        found = scan_urls(obj)
        for url in found:
            violations.append(f"{path}: {url}")

    return violations


def validate_catalog_membership(
    obj: Any,
    catalog_uris: Set[str],
    path: str = "",
) -> list[str]:
    """Check that every deeplink value exists in the catalog set."""
    violations = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else k
            if k == "deeplink" and isinstance(v, str):
                if v not in catalog_uris:
                    violations.append(f"{child_path}: '{v}' not in catalog")
            else:
                violations.extend(validate_catalog_membership(v, catalog_uris, child_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(validate_catalog_membership(item, catalog_uris, f"{path}[{i}]"))

    return violations


def validate_goal_format(goal: str) -> bool:
    """Check that goal matches the required format."""
    return bool(_GOAL_RE.match(goal))


def validate_title(title: str) -> bool:
    """Check title is 2-3 words, sentence case."""
    words = title.split()
    if not (TITLE_WORDS[0] <= len(words) <= TITLE_WORDS[1]):
        return False
    # First word capitalized
    if not words[0][0].isupper():
        return False
    return True


def validate_description(desc: str) -> bool:
    """Check description starts with 'It will' and is 5-7 words."""
    if not desc.startswith("It will"):
        return False
    words = desc.rstrip(".").split()
    return DESC_WORDS[0] <= len(words) <= DESC_WORDS[1]


def validate_steps(steps: list[str]) -> list[str]:
    """Validate that steps are non-empty, end with period, no URLs."""
    issues = []
    for i, step in enumerate(steps):
        if not step.strip():
            issues.append(f"Step {i}: empty")
        if not step.rstrip().endswith("."):
            issues.append(f"Step {i}: does not end with period")
        urls = scan_urls(step)
        if urls:
            issues.append(f"Step {i}: contains URL: {urls}")
    return issues


def validate_ordering(actions: list[Action]) -> bool:
    """Check that actions are ordered: auto -> manual -> critical."""
    last_order = -1
    for action in actions:
        cat = action.category.value if action.category else "manual"
        order = CATEGORY_ORDER.get(cat, 1)
        if order < last_order:
            return False
        last_order = order
    return True


def validate_manual_no_deeplink(actions: list[Action]) -> list[str]:
    """Check that manual actions have no actionable deeplink."""
    issues = []
    for i, action in enumerate(actions):
        if action.category == actionCategory.manual:
            for j, sg in enumerate(action.stepGroups):
                if sg.actionableDeeplink is not None:
                    issues.append(f"Action {i} stepGroup {j}: manual has actionableDeeplink")
    return issues


# ── Auto-fix functions ────────────────────────────────────────────────

def fix_description(desc: str) -> str:
    """Auto-fix a description to conform to rules."""
    return enforce_description(desc)


def fix_title(title: str) -> str:
    """Auto-fix a title to 2-3 words, sentence case."""
    title = to_sentence_case(title)
    words = title.split()
    if len(words) > TITLE_WORDS[1]:
        words = words[:TITLE_WORDS[1]]
    elif len(words) < TITLE_WORDS[0]:
        words.append("issue")
    return " ".join(words)


def fix_step(step: str) -> str:
    """Auto-fix a step: scrub URLs, ensure period ending."""
    step = scrub_urls(step)
    step = step.strip()
    if step and not step.endswith("."):
        step += "."
    return step


def fix_ordering(actions: list[Action]) -> list[Action]:
    """Re-sort actions: auto -> manual -> critical (stable sort)."""
    return sorted(
        actions,
        key=lambda a: CATEGORY_ORDER.get(
            a.category.value if a.category else "manual", 1
        ),
    )


def fix_manual_deeplinks(actions: list[Action]) -> list[Action]:
    """Remove actionable deeplinks from manual actions."""
    for action in actions:
        if action.category == actionCategory.manual:
            for sg in action.stepGroups:
                if sg.actionableDeeplink is not None:
                    logger.warning(
                        "Removing deeplink from manual action: %s", action.actionName
                    )
                    sg.actionableDeeplink = None
    return actions


# ── Final gate ────────────────────────────────────────────────────────

def final_gate(
    response_dict: dict,
    catalog_uris: Set[str],
) -> dict:
    """Run all validations on a response dict.

    Applies auto-fixes where possible. Drops unfixable actions.
    Returns the cleaned response dict.
    """
    fixes_log: list[str] = []

    contexts = response_dict.get("response", {}).get("contexts", [])
    if not contexts:
        return response_dict

    cleaned_contexts = []
    for goal_dict in contexts:
        # Fix goal format
        goal_str = goal_dict.get("goal", "")
        if not validate_goal_format(goal_str):
            fixes_log.append(f"Goal format invalid: {goal_str}")
            # Can't auto-fix goal easily — keep as is (pipeline should generate correctly)

        # Fix title
        title = goal_dict.get("title", "")
        if not validate_title(title):
            fixed = fix_title(title)
            fixes_log.append(f"Title fixed: '{title}' -> '{fixed}'")
            goal_dict["title"] = fixed

        # Fix score range
        score = goal_dict.get("score", 0.0)
        if not (0.0 <= score <= 1.0):
            goal_dict["score"] = max(0.0, min(1.0, score))
            fixes_log.append(f"Score clamped: {score} -> {goal_dict['score']}")

        # Round score to 2 decimals
        goal_dict["score"] = round(goal_dict["score"], 2)

        # Process actions
        actions = goal_dict.get("actions", [])
        valid_actions = []

        for action_dict in actions:
            try:
                # Fix description
                desc = action_dict.get("description", "")
                if not validate_description(desc):
                    fixed = fix_description(desc)
                    fixes_log.append(f"Description fixed: '{desc}' -> '{fixed}'")
                    action_dict["description"] = fixed

                # Fix actionName to Title Case
                action_name = action_dict.get("actionName", "")
                fixed_name = to_title_case(action_name)
                if fixed_name != action_name:
                    fixes_log.append(f"ActionName casing fixed: '{action_name}' -> '{fixed_name}'")
                    action_dict["actionName"] = fixed_name

                # Fix steps
                for sg in action_dict.get("stepGroups", []):
                    fixed_steps = []
                    for step in sg.get("steps", []):
                        fixed = fix_step(step)
                        if fixed:
                            fixed_steps.append(fixed)
                        else:
                            fixes_log.append(f"Empty step dropped in {action_name}")
                    sg["steps"] = fixed_steps

                    # Validate step group has steps
                    if not sg["steps"]:
                        fixes_log.append(f"Empty stepGroup in {action_name}")
                        continue

                # Remove deeplinks from manual actions
                cat = action_dict.get("category", "manual")
                if cat == "manual":
                    for sg in action_dict.get("stepGroups", []):
                        if sg.get("actionableDeeplink") is not None:
                            fixes_log.append(
                                f"Removed deeplink from manual: {action_name}"
                            )
                            sg["actionableDeeplink"] = None

                # Validate catalog membership for deeplinks
                for sg in action_dict.get("stepGroups", []):
                    ad = sg.get("actionableDeeplink")
                    if ad and isinstance(ad, dict):
                        dl_uri = ad.get("deeplink", "")
                        if dl_uri and dl_uri not in catalog_uris:
                            fixes_log.append(
                                f"Deeplink not in catalog, nullifying: {dl_uri}"
                            )
                            sg["actionableDeeplink"] = None

                    vd = sg.get("validationDeeplink")
                    if vd and isinstance(vd, dict):
                        vl_uri = vd.get("deeplink", "")
                        if vl_uri and vl_uri not in catalog_uris:
                            fixes_log.append(
                                f"Validation deeplink not in catalog, nullifying: {vl_uri}"
                            )
                            sg["validationDeeplink"] = None

                # URL scrub all string fields (except deeplinks)
                _scrub_action_urls(action_dict, fixes_log)

                valid_actions.append(action_dict)

            except Exception as e:
                fixes_log.append(f"Action dropped due to error: {e}")
                logger.warning("Dropping action due to error: %s", e)

        # Cap actions
        if len(valid_actions) > MAX_ACTIONS_PER_GOAL:
            fixes_log.append(
                f"Capped actions from {len(valid_actions)} to {MAX_ACTIONS_PER_GOAL}"
            )
            valid_actions = valid_actions[:MAX_ACTIONS_PER_GOAL]

        # Re-sort ordering
        try:
            parsed_actions = [Action(**a) for a in valid_actions]
            if not validate_ordering(parsed_actions):
                parsed_actions = fix_ordering(parsed_actions)
                valid_actions = [a.model_dump(mode="json") for a in parsed_actions]
                fixes_log.append("Actions re-ordered for category compliance")
        except Exception as e:
            fixes_log.append(f"Ordering fix failed: {e}")

        goal_dict["actions"] = valid_actions

        # Only keep goals with actions (or empty for fallback)
        cleaned_contexts.append(goal_dict)

    response_dict["response"]["contexts"] = cleaned_contexts

    # Try to validate against schema
    try:
        ContextDeeplinkResponse(**response_dict["response"])
    except ValidationError as e:
        logger.error("Schema validation failed after fixes: %s", e)
        fixes_log.append(f"Schema validation failed: {e}")

    if fixes_log:
        logger.info("Final gate fixes: %s", fixes_log)

    return response_dict


def _scrub_action_urls(action_dict: dict, fixes_log: list[str]) -> None:
    """Scrub URLs from all string fields in an action, excluding deeplink fields."""
    for sg in action_dict.get("stepGroups", []):
        # Scrub steps
        cleaned_steps = []
        for step in sg.get("steps", []):
            cleaned = scrub_urls(step)
            if cleaned != step:
                fixes_log.append(f"URL scrubbed from step: '{step}' -> '{cleaned}'")
            cleaned_steps.append(cleaned)
        sg["steps"] = cleaned_steps

    # Scrub description
    desc = action_dict.get("description", "")
    cleaned = scrub_urls(desc)
    if cleaned != desc:
        fixes_log.append(f"URL scrubbed from description")
        action_dict["description"] = cleaned

    # Scrub actionName
    name = action_dict.get("actionName", "")
    cleaned = scrub_urls(name)
    if cleaned != name:
        action_dict["actionName"] = cleaned
