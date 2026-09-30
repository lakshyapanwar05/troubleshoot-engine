"""Load and index the deeplink catalog and SIIS data files."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import DEEPLINKS_PATH, SIIS_PATH, INPUT_PATH

logger = logging.getLogger(__name__)


def load_deeplinks(path: Path = DEEPLINKS_PATH) -> list[dict]:
    """Load the deeplink catalog.

    Returns list of deeplink entry dicts.
    Filters out entries with originalType == null (read-only, never use as actionable).
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    deeplinks = data.get("deeplinks", [])
    logger.info("Loaded %d deeplink entries", len(deeplinks))
    return deeplinks


def load_deeplinks_full(path: Path = DEEPLINKS_PATH) -> list[dict]:
    """Load ALL deeplink entries including null originalType (for validation URI set)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("deeplinks", [])


def build_catalog_uri_set(deeplinks: list[dict]) -> set[str]:
    """Build a set of all valid deeplink URIs for membership checks.

    Includes both actionable and validation deeplink URIs.
    """
    uris: set[str] = set()
    for entry in deeplinks:
        dl = entry.get("deeplink")
        if dl:
            uris.add(dl)
        val = entry.get("validation")
        if val and isinstance(val, dict):
            vdl = val.get("deeplink")
            if vdl:
                uris.add(vdl)
    return uris


def build_catalog_index(deeplinks: list[dict]) -> dict[str, dict]:
    """Build a dict mapping deeplink id -> entry for fast lookup."""
    return {entry["id"]: entry for entry in deeplinks}


def build_catalog_text_index(deeplinks: list[dict]) -> list[tuple[str, dict]]:
    """Build (searchable_text, entry) pairs for BM25/embedding indexing.

    Text is: message + description + qna_description (concatenated).
    Filters out null originalType and TV-only entries.
    """
    pairs = []
    for entry in deeplinks:
        otype = entry.get("originalType")
        if otype is None:
            continue  # Read-only entries, never use as actionable

        # Check for TV entries — skip them (will be included only on TV queries)
        desc = entry.get("description", "")
        msg = entry.get("message", "")
        if "via TV Settings" in desc or "via TV Settings" in msg:
            continue

        text_parts = [
            msg,
            desc,
            entry.get("qna_description", "") or "",
        ]
        search_text = " ".join(p for p in text_parts if p).strip()
        if search_text:
            pairs.append((search_text, entry))

    logger.info("Catalog text index: %d searchable entries", len(pairs))
    return pairs


def load_siis_responses(path: Path = SIIS_PATH) -> list[dict]:
    """Load SIIS responses.

    Returns list of {id, original_query, siis_response: {title, content}}.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    responses = data.get("responses", [])
    logger.info("Loaded %d SIIS responses", len(responses))
    return responses


def load_input_queries(path: Path = INPUT_PATH) -> list[str]:
    """Load input queries from input.txt, one per line, skip blanks."""
    with open(path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    logger.info("Loaded %d input queries", len(lines))
    return lines
