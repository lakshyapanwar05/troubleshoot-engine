"""Step group -> catalog deeplink matching, dummy fallback, validation copy.

Uses verb/type priors to prefer the correct originalType for each step chain.
Copies validation objects verbatim from the catalog.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.config import DL_THRESHOLD
from app.retrieval import CatalogRetriever

logger = logging.getLogger(__name__)

# ── Verb-to-originalType priors ──────────────────────────────────────

# Map action verbs to preferred originalType
_VERB_TYPE_MAP = {
    # Navigate/open/view -> onClickURL (opens a page)
    "navigate": "onClickURL",
    "open": "onClickURL",
    "go to": "onClickURL",
    "view": "onClickURL",
    "launch": "onClickURL",
    "check": "onClickURL",
    # Turn on/enable/toggle on -> onURL
    "turn on": "onURL",
    "enable": "onURL",
    "activate": "onURL",
    "toggle on": "onURL",
    # Turn off/disable -> offURL
    "turn off": "offURL",
    "disable": "offURL",
    "deactivate": "offURL",
    "toggle off": "offURL",
    # Adjust/slide/set -> updateURL
    "adjust": "updateURL",
    "slide": "updateURL",
    "set": "updateURL",
    "change": "updateURL",
}


def infer_type_prior(steps: list[str]) -> Optional[str]:
    """Infer the preferred originalType from step verbs.

    Looks at the LAST step (the actual action), not navigation steps.
    """
    if not steps:
        return None

    # Check last few steps for the actual action verb
    for step in reversed(steps):
        step_lower = step.lower().rstrip(".")
        for verb, otype in _VERB_TYPE_MAP.items():
            if step_lower.startswith(verb):
                return otype

    # Default: if it's a settings chain, prefer onClickURL
    if any("settings" in s.lower() for s in steps):
        return "onClickURL"

    return None


# ── Dummy deeplink entry ─────────────────────────────────────────────

DUMMY_ENTRY = {
    "id": "DL-DUMMY",
    "deeplink": "voiceassist://dummy_positive",
    "originalType": "placeholder",
}


def make_dummy_deeplink(screen_name: str) -> dict:
    """Create a dummy deeplink for a Settings screen with no catalog entry.

    Writes description and message as 5-7 words naming the concrete screen.
    """
    clean_name = re.sub(r"[^\w\s]", "", screen_name).strip()
    if not clean_name:
        clean_name = "Settings"

    # Build description (5-7 words)
    desc = f"Opens the {clean_name} settings screen."
    dwords = desc.split()
    if len(dwords) < 5:
        desc = f"Opens the {clean_name} page in device Settings."
        dwords = desc.split()
    if len(dwords) > 7:
        desc = " ".join(dwords[:7]).rstrip(".") + "."

    # Build message (5-7 words)
    msg = f"Open the {clean_name} settings screen"
    mwords = msg.split()
    if len(mwords) < 5:
        msg = f"Open {clean_name} in device Settings"
        mwords = msg.split()
    if len(mwords) > 7:
        msg = " ".join(mwords[:7])

    return {
        "deeplink": DUMMY_ENTRY["deeplink"],
        "description": desc,
        "message": msg,
        "originalType": "placeholder",
    }


def extract_target_terms(steps: list[str], heading: str, action_name: str) -> list[str]:
    """Extract concrete target feature/screen names from steps, heading, and action name.

    The chain's target screen/feature is the last navigation tap or heading.
    """
    targets = []
    # Find the last concrete navigation tap (target screen)
    for s in reversed(steps):
        m = re.search(r"(?:tap(?:\s+on)?|select|go\s+to|open|choose)\s+([A-Z][a-zA-Z0-9\s/]+?)(?:\.|\s+to|\s+when|\s+and|$)", s, re.IGNORECASE)
        if m:
            t = m.group(1).strip()
            if t.lower() not in {"settings", "and", "buttons", "ok", "more options", "the power icon", "apps", "app", "restart", "safe mode"}:
                targets.append(t)
                break

    # Check action name and heading
    for name in [action_name, heading]:
        if name:
            clean = re.sub(r"^(?:Step\s+)?\d+[.:)]\s*", "", name, flags=re.IGNORECASE)
            clean = re.sub(r"\b(?:issues?|troubleshooting|smartphone|tablet|device|phone|your|the|a|an)\b", "", clean, flags=re.IGNORECASE).strip()
            if clean and len(clean) > 2:
                targets.append(clean)
    return targets


def has_lexical_evidence(targets: list[str], entry: dict) -> bool:
    """Check if the chain's target screen/feature name overlaps catalog message or description."""
    if not targets:
        return False

    msg = entry.get("message", "").lower()
    desc = entry.get("description", "").lower()
    combined_entry = f"{msg} {desc}"

    stopwords = {
        "a", "an", "the", "on", "in", "to", "for", "with", "of", "and", "or",
        "settings", "view", "open", "page", "device", "screen", "tap", "select",
        "step", "troubleshooting", "smartphone", "tablet", "phone", "your",
        "apps", "app", "general", "menu", "option", "options"
    }

    for target in targets:
        target_lower = target.lower()
        # Direct substring check for multi-word targets like "navigation bar"
        if len(target_lower) > 3 and target_lower in combined_entry:
            return True
        # Token overlap check: at least one distinctive target word must appear in the entry
        words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", target_lower) if w not in stopwords]
        # For targets with multiple words (e.g. "navigation bar"), require all words to match
        if len(words) >= 2:
            if all(re.search(r"\b" + re.escape(w) + r"\b", combined_entry) for w in words):
                return True
        elif len(words) == 1:
            w = words[0]
            if re.search(r"\b" + re.escape(w) + r"\b", combined_entry):
                return True

    return False


# ── Main matching function ───────────────────────────────────────────

def match_deeplink(
    steps: list[str],
    action_name: str,
    section_heading: str,
    category: str,
    catalog_retriever: CatalogRetriever,
    catalog_uris: set[str],
) -> tuple[Optional[dict], Optional[dict]]:
    """Match a step chain to a catalog deeplink.

    Returns (actionable_deeplink_dict, validation_deeplink_dict).
    Both may be None.

    For manual actions, always returns (None, None).
    """
    # Manual actions never get deeplinks
    if category == "manual":
        return None, None

    # Extract navigation targets from steps (e.g. "tap Display", "tap Navigation bar")
    nav_targets = []
    for s in steps:
        m = re.search(r"(?:tap(?:\s+on)?|select|go\s+to|open)\s+([A-Z][a-zA-Z\s]+?)(?:\.|$)", s, re.IGNORECASE)
        if m:
            target = m.group(1).strip()
            if target.lower() not in {"settings", "and", "buttons"}:
                nav_targets.append(target)

    # Build query prioritizing concrete screen targets
    query_parts = []
    if nav_targets:
        query_parts.append(nav_targets[-1])  # Most specific target screen
        query_parts.extend(nav_targets)

    for s in steps:
        query_parts.append(s.strip().rstrip("."))
    if action_name:
        query_parts.append(action_name)
    if section_heading and section_heading != action_name:
        query_parts.append(section_heading)

    query = " ".join(query_parts)

    # Determine preferred type from step verbs
    type_prior = infer_type_prior(steps)

    # Search catalog with type prior
    results = catalog_retriever.search(query, top_k=5, type_filter=type_prior)

    # If no results with type filter, try without
    if not results:
        results = catalog_retriever.search(query, top_k=5)

    # Extract target terms for lexical evidence verification
    target_terms = extract_target_terms(steps, section_heading, action_name)

    # Filter candidates: must pass DL_THRESHOLD AND have lexical evidence
    matched_entry = None
    matched_score = 0.0

    for entry, score in results:
        if score >= DL_THRESHOLD and has_lexical_evidence(target_terms, entry):
            matched_entry = entry
            matched_score = score
            break

    if not matched_entry:
        # No confident real catalog match — use dummy if settings chain, else None
        if _is_settings_chain(steps):
            screen_name = _extract_screen_name(steps, action_name)
            dummy = make_dummy_deeplink(screen_name)
            return dummy, None
        return None, None

    logger.debug(
        "Deeplink confident match: query='%s' -> id=%s score=%.3f type=%s",
        query[:60], matched_entry.get("id"), matched_score, matched_entry.get("originalType"),
    )

    # Build the actionable deeplink (copy only required fields)
    dl_uri = matched_entry.get("deeplink", "")

    # Verify URI exists in catalog
    if dl_uri not in catalog_uris:
        logger.warning("Deeplink URI not in catalog set: %s", dl_uri)
        if _is_settings_chain(steps):
            screen_name = _extract_screen_name(steps, action_name)
            dummy = make_dummy_deeplink(screen_name)
            return dummy, None
        return None, None

    actionable = {
        "deeplink": dl_uri,
        "description": matched_entry.get("description", ""),
        "message": matched_entry.get("message", ""),
        "originalType": matched_entry.get("originalType"),
    }

    # Copy validation verbatim
    validation = _copy_validation(matched_entry, catalog_uris)

    return actionable, validation


def _copy_validation(entry: dict, catalog_uris: set[str]) -> Optional[dict]:
    """Copy the validation object verbatim from the catalog entry."""
    val = entry.get("validation")
    if not val or not isinstance(val, dict):
        return None

    val_dl = val.get("deeplink")
    if not val_dl:
        return None

    # Verify validation deeplink exists
    if val_dl not in catalog_uris:
        logger.warning("Validation deeplink not in catalog: %s", val_dl)
        return None

    # Copy verbatim — include all fields present
    result = {"deeplink": val_dl, "key": val.get("key", "")}

    # Add optional fields if present
    if "resultType" in val and val["resultType"] is not None:
        result["resultType"] = val["resultType"]
    if "condition" in val and val["condition"] is not None:
        result["condition"] = val["condition"]
    if "value" in val and val["value"] is not None:
        result["value"] = val["value"]

    return result


def _is_settings_chain(steps: list[str]) -> bool:
    """Check if the steps represent a Settings navigation chain."""
    return any(re.search(r"\b(?:open|navigate\s+(?:to\s+and\s+)?open)\s+Settings\b", s, re.IGNORECASE) for s in steps)


def _extract_screen_name(steps: list[str], action_name: str) -> str:
    """Extract the screen name from steps for dummy deeplink."""
    # Use the last tap target as the screen name
    for step in reversed(steps):
        m = re.match(r"(?:Tap|Tap on|Select|Touch)\s+(.+?)\.$", step, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # Fall back to action name
    return action_name
