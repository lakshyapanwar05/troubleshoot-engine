"""Semantic cache — numpy matrix + JSON persistence.

Lookup flow:
1. Exact normalized-string dict first
2. If miss, max cosine similarity over the embedding matrix
3. Hit if >= CACHE_THRESHOLD
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import CACHE_DIR, CACHE_THRESHOLD, CACHE_VECTORS_PATH, CACHE_INDEX_PATH
from app.retrieval import encode_single, encode_texts

logger = logging.getLogger(__name__)


class SemanticCache:
    """Semantic cache with exact-match dict + embedding matrix fallback."""

    def __init__(self):
        self.exact_map: dict[str, dict] = {}  # normalized_query -> plan_dict
        self.embeddings: Optional[np.ndarray] = None  # (N, dim) matrix
        self.keys: list[str] = []  # index -> normalized_query
        self._dirty = False

    def _normalize_key(self, query: str) -> str:
        """Normalize query for exact-match lookup."""
        return query.lower().strip().rstrip(".")

    def put(self, query: str, plan: dict, variations: list[str] = None) -> None:
        """Add a query and its plan to the cache.

        Also indexes all variations for better cache hit rate.
        """
        norm_key = self._normalize_key(query)
        self.exact_map[norm_key] = plan

        # Embed the query and all variations
        texts_to_embed = [query]
        if variations:
            texts_to_embed.extend(variations)
            # Also add variations to exact map
            for v in variations:
                v_key = self._normalize_key(v)
                if v_key not in self.exact_map:
                    self.exact_map[v_key] = plan

        new_embeddings = encode_texts(texts_to_embed)

        if self.embeddings is None:
            self.embeddings = new_embeddings
            self.keys = [self._normalize_key(t) for t in texts_to_embed]
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])
            self.keys.extend([self._normalize_key(t) for t in texts_to_embed])

        self._dirty = True

    def get(self, query: str) -> Optional[dict]:
        """Look up a query in the cache.

        Returns plan dict on hit, None on miss.
        """
        norm_key = self._normalize_key(query)

        # 1. Exact match
        if norm_key in self.exact_map:
            logger.debug("Cache exact hit: %s", query[:50])
            return self.exact_map[norm_key]

        # 2. Semantic similarity
        if self.embeddings is not None and len(self.embeddings) > 0:
            query_emb = encode_single(query)
            similarities = self.embeddings @ query_emb
            best_idx = int(np.argmax(similarities))
            best_score = float(similarities[best_idx])

            logger.debug(
                "Cache semantic lookup: query='%s' best_key='%s' score=%.3f threshold=%.3f",
                query[:40], self.keys[best_idx][:40], best_score, CACHE_THRESHOLD,
            )

            if best_score >= CACHE_THRESHOLD:
                best_key = self.keys[best_idx]
                if best_key in self.exact_map:
                    logger.debug("Cache semantic hit: score=%.3f", best_score)
                    return self.exact_map[best_key]

        return None

    def save(self) -> None:
        """Persist cache to disk."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if self.embeddings is not None:
            np.save(str(CACHE_VECTORS_PATH), self.embeddings)

        index_data = {
            "keys": self.keys,
            "exact_map_keys": list(self.exact_map.keys()),
            "plans": {k: v for k, v in self.exact_map.items()},
        }
        with open(CACHE_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index_data, f, ensure_ascii=False)

        self._dirty = False
        logger.info(
            "Cache saved: %d exact entries, %d embeddings",
            len(self.exact_map), len(self.keys),
        )

    def load(self) -> bool:
        """Load cache from disk. Returns True if loaded successfully."""
        if not CACHE_INDEX_PATH.exists():
            return False

        try:
            with open(CACHE_INDEX_PATH, "r", encoding="utf-8") as f:
                index_data = json.load(f)

            self.keys = index_data.get("keys", [])
            self.exact_map = index_data.get("plans", {})

            if CACHE_VECTORS_PATH.exists():
                self.embeddings = np.load(str(CACHE_VECTORS_PATH))
                if self.embeddings.shape[0] != len(self.keys):
                    logger.warning(
                        "Cache vectors/keys mismatch: %d vs %d, resetting",
                        self.embeddings.shape[0], len(self.keys),
                    )
                    self.embeddings = None
                    self.keys = []
                    self.exact_map = {}
                    return False

            logger.info(
                "Cache loaded: %d exact entries, %d embeddings",
                len(self.exact_map), len(self.keys),
            )
            return True
        except Exception as e:
            logger.warning("Cache load failed: %s", e)
            return False

    def clear(self) -> None:
        """Clear all in-memory entries."""
        self.exact_map = {}
        self.embeddings = None
        self.keys = []
        self._dirty = True

    @property
    def size(self) -> int:
        return len(self.exact_map)
