"""Deterministic rule-based paraphrase generator.

Generates 8-10 distinct query variations across registers:
formal, casual, keyword-only, frustrated, typo-inclusive, synonym swaps.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

import yaml

from app.config import RULES_DIR

_synonyms_data: Optional[dict] = None


def _load_synonyms() -> dict:
    global _synonyms_data
    if _synonyms_data is None:
        with open(RULES_DIR / "synonyms.yaml", "r", encoding="utf-8") as f:
            _synonyms_data = yaml.safe_load(f)
    return _synonyms_data


def _build_synonym_map() -> dict[str, list[str]]:
    """Build a bidirectional synonym lookup: word -> [synonyms]."""
    data = _load_synonyms()
    syn_map: dict[str, list[str]] = {}

    for canonical, synonyms in data.items():
        if not isinstance(synonyms, list):
            continue
        all_terms = [canonical] + synonyms
        for term in all_terms:
            term_lower = term.lower()
            others = [t for t in all_terms if t.lower() != term_lower]
            if term_lower in syn_map:
                syn_map[term_lower] = list(set(syn_map[term_lower] + others))
            else:
                syn_map[term_lower] = others

    return syn_map


def _hash_seed(text: str) -> int:
    """Deterministic seed from query text for reproducible typo insertion."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def _apply_synonym_swap(text: str, syn_map: dict[str, list[str]], variant: int) -> str:
    """Apply deterministic synonym swaps to text."""
    words = text.split()
    result = []
    swap_count = 0

    for word in words:
        clean = word.lower().rstrip(".,!?;:'\"")
        if clean in syn_map and syn_map[clean]:
            # Use variant index to pick which synonym
            alternatives = syn_map[clean]
            idx = (variant + swap_count) % len(alternatives)
            replacement = alternatives[idx]
            # Preserve original punctuation
            trailing = word[len(clean):]
            if word[0].isupper():
                replacement = replacement.capitalize()
            result.append(replacement + trailing)
            swap_count += 1
        else:
            result.append(word)

    return " ".join(result)


def _make_formal(text: str) -> str:
    """Formal register: polite, complete sentences."""
    text = text.rstrip(".")
    prefixes = [
        "I am experiencing an issue where",
        "I would like to report that",
    ]
    # Pick deterministically
    idx = len(text) % len(prefixes)
    return f"{prefixes[idx]} {text.lower()}."


def _make_casual(text: str) -> str:
    """Casual register: short, informal."""
    text = text.rstrip(".")
    # Strip leading "My" and simplify
    text = re.sub(r"^My\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r",?\s+(?:and|so)\s+I\s+can't\s+", ", can't ", text, flags=re.IGNORECASE)
    text = re.sub(r",+", ",", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    return f"hey my {text.lower()}."


def _make_keyword_only(text: str) -> str:
    """Keyword-only register: stop words removed."""
    stop_words = {
        "my", "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "shall", "should", "may", "might", "can", "could", "i", "me", "we",
        "you", "he", "she", "it", "they", "them", "that", "this", "these",
        "those", "and", "but", "or", "so", "if", "when", "while", "as",
        "to", "of", "in", "on", "at", "for", "with", "from", "by", "about",
        "into", "through", "after", "before", "up", "down", "out", "off",
        "just", "also", "very", "really", "quite", "even", "still", "again",
        "too", "not", "no", "don't", "doesn't", "didn't", "won't", "can't",
        "couldn't", "shouldn't", "wouldn't", "isn't", "aren't", "wasn't",
        "weren't", "hasn't", "haven't", "hadn't",
    }
    words = text.split()
    filtered = [w for w in words if w.lower().rstrip(".,!?;:'\"") not in stop_words]
    return " ".join(filtered).rstrip(".") if filtered else text


def _make_frustrated(text: str) -> str:
    """Frustrated register: emphatic, urgent tone."""
    text = text.rstrip(".")
    suffixes = [
        " and it's really frustrating!",
        " - this is unacceptable, please help!",
        " and nothing works, I need help NOW!",
    ]
    idx = len(text) % len(suffixes)
    return text + suffixes[idx]


def _make_typo(text: str) -> str:
    """Typo-inclusive variant: introduce deterministic typos."""
    seed = _hash_seed(text)
    words = text.split()
    if len(words) < 3:
        return text

    result = list(words)

    # Pick which word to modify (deterministic)
    word_idx = seed % len(words)
    word = result[word_idx]

    if len(word) > 3:
        # Swap two adjacent characters
        char_idx = (seed >> 4) % (len(word) - 1)
        chars = list(word)
        chars[char_idx], chars[char_idx + 1] = chars[char_idx + 1], chars[char_idx]
        result[word_idx] = "".join(chars)
    elif len(word) > 1:
        # Drop a character
        char_idx = (seed >> 4) % len(word)
        result[word_idx] = word[:char_idx] + word[char_idx + 1:]

    return " ".join(result)


def generate_variations(query: str, count: int = 10) -> list[str]:
    """Generate 8-10 distinct paraphrases of a query.

    Covers: formal, casual, keyword-only, frustrated, typo-inclusive,
    and synonym-swap variants. Deterministic output.
    """
    syn_map = _build_synonym_map()
    variations: list[str] = []
    seen: set[str] = {query.lower().strip()}

    def _add(v: str) -> None:
        v = v.strip()
        v = re.sub(r",+", ",", v)
        v = re.sub(r"\s*,\s*", ", ", v)
        if v and v.lower() not in seen:
            seen.add(v.lower())
            variations.append(v)

    # 1. Formal variant
    _add(_make_formal(query))

    # 2. Casual variant
    _add(_make_casual(query))

    # 3. Keyword-only
    _add(_make_keyword_only(query))

    # 4. Frustrated variant
    _add(_make_frustrated(query))

    # 5. Typo variant
    _add(_make_typo(query))

    # 6-8. Synonym swap variants
    for i in range(3):
        swapped = _apply_synonym_swap(query, syn_map, variant=i)
        _add(swapped)

    # 9-10. Combined variants (synonym + register)
    swapped = _apply_synonym_swap(query, syn_map, variant=3)
    _add(_make_casual(swapped))
    _add(_make_formal(swapped))

    # If we still need more, create additional synonym swaps
    extra_idx = 4
    while len(variations) < 8:
        swapped = _apply_synonym_swap(query, syn_map, variant=extra_idx)
        _add(swapped)
        _add(_make_frustrated(swapped))
        extra_idx += 1
        if extra_idx > 10:
            break

    # Ensure we have at least 8 and at most count
    # If still short, add simple reformulations
    if len(variations) < 8:
        _add(query.rstrip(".") + " on my device.")
        _add("My device: " + query.lower().rstrip(".") + ".")
        _add("Issue: " + query.lower().rstrip(".") + ".")

    return variations[:count]
