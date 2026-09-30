"""Query cleaning, multi-intent split, canonical query generation."""
from __future__ import annotations

import re
from typing import List

from app.config import BRAND_MODEL_PATTERN, BRAND_TOKENS, MAX_GOALS


def strip_enumerators(text: str) -> str:
    """Strip leading enumerators like '1.', '2)', etc. and surrounding quotes."""
    # Remove leading number + punctuation
    text = re.sub(r"^\s*\d+[.)]\s*", "", text)
    # Remove surrounding quotes
    text = text.strip('"\'""''')
    return text.strip()


def split_multi_intent(text: str) -> List[str]:
    """Split multi-intent queries into sub-queries.

    Detects patterns like:
      1. "query one" 2. "query two" 3. "query three"
    or numbered items on separate lines.

    Returns a list of sub-queries (max MAX_GOALS).
    """
    # Pattern: numbered items with quotes on same line
    # e.g., 1. "query" 2. "query" 3. "query"
    pattern = r'\d+[.)]\s*["""]([^"""]+)["""]'
    matches = re.findall(pattern, text)

    if len(matches) >= 2:
        return [m.strip() for m in matches[:MAX_GOALS]]

    # Pattern: numbered items on separate lines
    lines = text.strip().split("\n")
    if len(lines) >= 2:
        numbered = []
        for line in lines:
            cleaned = strip_enumerators(line.strip())
            if cleaned:
                numbered.append(cleaned)
        if len(numbered) >= 2:
            return numbered[:MAX_GOALS]

    # Single query
    return [strip_enumerators(text)]


def canonicalize_query(text: str) -> str:
    """Build a device-agnostic canonical query for cache keys.

    - Replace brand/model tokens with 'phone/tablet/device'
    - Collapse whitespace
    - Sentence case
    - End with period
    """
    # Replace tablet-specific brand mentions
    query = re.sub(r"\b(?:techcorp\s+)?(?:[a-z0-9]+\s+)?tablet\b", "tablet", text, flags=re.IGNORECASE)
    # Replace smartphone with phone
    query = re.sub(r"\bsmartphone'?s?\b", "phone", query, flags=re.IGNORECASE)
    # Replace known brand + model combos with phone
    query = re.sub(r"\b(?:techcorp\s+)?nexa\s+(?:fold\s+)?(?:x1\s+ultra|x1|a14/a15|a14|a15)\b", "phone", query, flags=re.IGNORECASE)
    query = re.sub(r"\btechcorp\s+(?:x1\s+ultra|a15g|a14|a15)\b", "phone", query, flags=re.IGNORECASE)
    # Replace standalone brand names with device
    query = re.sub(r"\b(?:techcorp|nexa)\b", "device", query, flags=re.IGNORECASE)
    # Strip any remaining standalone model tokens
    query = re.sub(r"\b(?:x1|ultra|a14|a15|a15g)\b", "", query, flags=re.IGNORECASE)

    # Clean up redundant device words
    query = re.sub(r"\b(?:phone|device)\s+tablet\b", "tablet", query, flags=re.IGNORECASE)
    query = re.sub(r"\bdevice\s+phone\b", "phone", query, flags=re.IGNORECASE)
    query = re.sub(r"\bphone\s+phone\b", "phone", query, flags=re.IGNORECASE)

    # Collapse whitespace
    canonical = re.sub(r"\s+", " ", query).strip()

    # Sentence case
    if canonical:
        canonical = canonical[0].upper() + canonical[1:].lower() if len(canonical) > 1 else canonical.upper()

    # End with period
    if canonical and not canonical.endswith("."):
        canonical += "."

    return canonical


def normalize_query(raw_query: str) -> dict:
    """Full normalization pipeline.

    Returns {
        'original': str,
        'sub_queries': [str, ...],
        'canonical_queries': [str, ...],
        'is_multi_intent': bool
    }
    """
    sub_queries = split_multi_intent(raw_query)
    canonical_queries = [canonicalize_query(q) for q in sub_queries]

    return {
        "original": raw_query,
        "sub_queries": sub_queries,
        "canonical_queries": canonical_queries,
        "is_multi_intent": len(sub_queries) > 1,
    }
