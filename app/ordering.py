"""Action ordering: auto -> manual -> critical (stable sort).

Never put a critical action before a non-critical one.
"""
from __future__ import annotations

from app.config import CATEGORY_ORDER


def order_actions(actions: list[dict]) -> list[dict]:
    """Sort actions by category: auto -> manual -> critical.

    Uses stable sort to preserve source order within each category.
    """
    return sorted(
        actions,
        key=lambda a: CATEGORY_ORDER.get(a.get("category", "manual"), 1),
    )
