"""Category classification: auto / manual / critical.

Uses rules/categories.yaml keyword/regex lists.
First match wins in priority order: critical, manual, auto.
"""
from __future__ import annotations

import re
from typing import Optional

import yaml

from app.config import RULES_DIR

_categories_data: Optional[dict] = None


def _load_categories() -> dict:
    global _categories_data
    if _categories_data is None:
        with open(RULES_DIR / "categories.yaml", "r", encoding="utf-8") as f:
            _categories_data = yaml.safe_load(f)
    return _categories_data


def classify_action(steps: list[str], heading: str = "") -> str:
    """Classify an action's category from its steps and heading.

    Priority: critical > manual > auto.
    Returns one of: 'auto', 'manual', 'critical'.
    """
    data = _load_categories()
    all_text = " ".join(steps).lower() + " " + heading.lower()

    # Check critical first (highest priority)
    if _matches_category(all_text, data.get("critical", {})):
        return "critical"

    # Check manual
    if _matches_category(all_text, data.get("manual", {})):
        return "manual"

    # Check auto
    if _matches_category(all_text, data.get("auto", {})):
        return "auto"

    # Default: if steps mention settings navigation, it's auto
    if any("settings" in s.lower() for s in steps):
        return "auto"

    # Default to manual for physical/unclassified actions
    return "manual"


def _matches_category(text: str, category_data: dict) -> bool:
    """Check if text matches any keyword or pattern in a category."""
    # Check keywords with word boundaries
    keywords = category_data.get("keywords", [])
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text):
            return True

    # Check regex patterns
    patterns = category_data.get("patterns", [])
    for pat in patterns:
        if re.search(pat, text):
            return True

    return False
