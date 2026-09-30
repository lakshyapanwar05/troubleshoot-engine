"""Optional LLM hook via Ollama — OFF by default.

May only be used for:
(a) offline paraphrase augmentation
(b) polishing actionName/description wording

Never chooses steps, categories, or deeplinks.
Any LLM text must pass the same validators.
"""
from __future__ import annotations

import logging

from app.config import USE_LLM

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Check if LLM features are enabled."""
    return USE_LLM


def polish_description(description: str, context: str = "") -> str:
    """Polish a description using local Ollama model.

    Falls back to the original if LLM is disabled or fails.
    """
    if not USE_LLM:
        return description

    # Placeholder for Ollama integration
    logger.info("LLM polishing is enabled but not implemented yet")
    return description


def polish_action_name(name: str, context: str = "") -> str:
    """Polish an action name using local Ollama model."""
    if not USE_LLM:
        return name

    logger.info("LLM polishing is enabled but not implemented yet")
    return name
