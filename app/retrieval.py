"""BM25 + dense hybrid retrieval (RRF) over catalog and SIIS sections.

Provides:
- Catalog search (for deeplink matching)
- Section relevance scoring (for the relevance gate)
- Precomputed embedding caching
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import (
    CATALOG_EMB_PATH,
    CACHE_DIR,
    EMBEDDING_MODEL_NAME,
    RRF_K,
)

logger = logging.getLogger(__name__)

# ── Lazy-loaded embedding model ──────────────────────────────────────
_model = None


def get_model():
    """Lazy-load the sentence-transformer model from local path."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model from: %s", EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded successfully")
    return _model


def encode_texts(texts: list[str]) -> np.ndarray:
    """Encode a list of texts into embeddings."""
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return np.array(embeddings, dtype=np.float32)


def encode_single(text: str) -> np.ndarray:
    """Encode a single text string."""
    return encode_texts([text])[0]


# ── BM25 index ────────────────────────────────────────────────────────

class BM25Index:
    """BM25 index over a corpus of documents."""

    def __init__(self, documents: list[str]):
        tokenized = [doc.lower().split() for doc in documents]
        self.bm25 = BM25Okapi(tokenized)
        self.documents = documents

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """Search and return (index, score) pairs sorted by score desc."""
        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)

        # Normalize scores to [0, 1] — clip negative values (from negative IDF in small corpora)
        scores = np.maximum(scores, 0.0)
        max_score = scores.max() if scores.max() > 0 else 1.0
        normalized = scores / max_score

        # Get top-k indices
        top_indices = np.argsort(normalized)[::-1][:top_k]
        return [(int(idx), float(normalized[idx])) for idx in top_indices]


# ── Dense index ───────────────────────────────────────────────────────

class DenseIndex:
    """Dense embedding index using numpy cosine similarity."""

    def __init__(self, embeddings: np.ndarray):
        """Initialize with precomputed L2-normalized embeddings."""
        self.embeddings = embeddings

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> list[tuple[int, float]]:
        """Search by cosine similarity. query_embedding must be L2-normalized."""
        # Cosine similarity = dot product for normalized vectors
        scores = self.embeddings @ query_embedding
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(int(idx), float(scores[idx])) for idx in top_indices]


# ── Reciprocal Rank Fusion ────────────────────────────────────────────

def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[int, float]]],
    k: int = RRF_K,
) -> list[tuple[int, float]]:
    """Fuse multiple ranked lists using RRF.

    Each list is [(index, score), ...] sorted by score desc.
    Returns fused [(index, fused_score)] sorted by fused_score desc.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, (idx, _) in enumerate(ranked):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)

    # Sort by fused score descending
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused


# ── Hybrid retriever ──────────────────────────────────────────────────

class HybridRetriever:
    """Combined BM25 + dense retriever with RRF fusion."""

    def __init__(
        self,
        documents: list[str],
        embeddings: Optional[np.ndarray] = None,
    ):
        self.documents = documents
        self.bm25_index = BM25Index(documents)

        if embeddings is not None:
            self.dense_index = DenseIndex(embeddings)
        else:
            # Compute embeddings
            self.dense_index = DenseIndex(encode_texts(documents))

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """Hybrid search with RRF fusion.

        Returns [(doc_index, fused_score)] sorted by score desc.
        """
        # BM25 search
        bm25_results = self.bm25_index.search(query, top_k=top_k * 2)

        # Dense search
        query_emb = encode_single(query)
        dense_results = self.dense_index.search(query_emb, top_k=top_k * 2)

        # RRF fusion
        fused = reciprocal_rank_fusion([bm25_results, dense_results])

        return fused[:top_k]


# ── Catalog retriever (precomputed embeddings) ───────────────────────

class CatalogRetriever:
    """Retriever specifically for the deeplink catalog.

    Precomputes and caches embeddings to disk.
    """

    def __init__(self, catalog_texts: list[str], catalog_entries: list[dict]):
        self.catalog_texts = catalog_texts
        self.catalog_entries = catalog_entries

        # Load or compute embeddings
        embeddings = self._load_or_compute_embeddings()
        self.retriever = HybridRetriever(catalog_texts, embeddings)

    def _load_or_compute_embeddings(self) -> np.ndarray:
        """Load cached embeddings or compute and cache them."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if CATALOG_EMB_PATH.exists():
            logger.info("Loading cached catalog embeddings from %s", CATALOG_EMB_PATH)
            emb = np.load(str(CATALOG_EMB_PATH))
            if emb.shape[0] == len(self.catalog_texts):
                return emb
            logger.warning("Cached embeddings size mismatch, recomputing")

        logger.info("Computing catalog embeddings for %d entries", len(self.catalog_texts))
        emb = encode_texts(self.catalog_texts)
        np.save(str(CATALOG_EMB_PATH), emb)
        logger.info("Catalog embeddings cached to %s", CATALOG_EMB_PATH)
        return emb

    def search(
        self,
        query: str,
        top_k: int = 5,
        type_filter: Optional[str] = None,
    ) -> list[tuple[dict, float]]:
        """Search catalog, optionally filtering by originalType.

        Returns [(catalog_entry, fused_score)].
        """
        results = self.retriever.search(query, top_k=top_k * 3)

        # Max theoretical score for 2 rankers with constant RRF_K
        max_rrf = 2.0 / (RRF_K + 1)

        # Apply type filter if specified
        filtered = []
        for idx, score in results:
            entry = self.catalog_entries[idx]
            if type_filter:
                if entry.get("originalType") != type_filter:
                    continue
            norm_score = min(score / max_rrf, 1.0)
            filtered.append((entry, norm_score))
            if len(filtered) >= top_k:
                break

        return filtered


# ── Section relevance scorer ──────────────────────────────────────────

def score_sections(
    query: str,
    sections: list[tuple[str, str]],
) -> list[tuple[tuple[str, str], float]]:
    """Score sections against a query using blended cosine + BM25.

    Returns [(section, score)] sorted by score desc.
    Scores are on [0, 1] scale (cosine-similarity dominant) so they
    can be compared directly against REL_THRESHOLD.
    """
    if not sections:
        return []

    # Build text for each section
    section_texts = [f"{heading} {body}" for heading, body in sections]

    # Dense cosine similarity (primary signal, already on [0,1] for normalized vecs)
    section_embs = encode_texts(section_texts)
    query_emb = encode_single(query)
    cosine_scores = section_embs @ query_emb  # shape (N,)

    # BM25 normalized scores (secondary signal)
    bm25 = BM25Index(section_texts)
    bm25_results = bm25.search(query, top_k=len(sections))
    bm25_map = {idx: score for idx, score in bm25_results}

    # Blend: 0.7 * cosine + 0.3 * BM25_normalized
    scored = []
    for i, section in enumerate(sections):
        cos = float(cosine_scores[i])
        bm = bm25_map.get(i, 0.0)
        blended = 0.7 * cos + 0.3 * bm
        scored.append((section, blended))

    # Sort descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
