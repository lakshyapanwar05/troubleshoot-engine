# Phase 4 Report: Pipeline

## What Was Built
- `app/pipeline.py` — full orchestration: normalize → section → extract → classify → deeplink match → order → validate
- `app/variations.py` — deterministic 8-10 paraphrase generator (formal, casual, keyword-only, frustrated, typo, synonym swap)
- `app/cache.py` — semantic cache with exact-match dict + cosine similarity embedding matrix, persisted to disk
- `app/main.py` — FastAPI app with startup prewarm and /health + /v1/troubleshoot endpoints
- `app/llm_optional.py` — OFF by default stub for optional Ollama polishing

## Test Results
**54/54 tests passed** covering:
- Schema conformance for all 20 rows ✅
- URL-leak scan over every output string ✅
- Catalog membership for every deeplink ✅
- Word-count and casing rules ✅
- Ordering rule (auto → manual → critical) ✅
- Manual actions have no deeplink ✅
- Determinism (same input → same output) ✅
- Multi-intent (row_19 with 3 complaints → 3 goals) ✅
- Negative: no_siis_context and no_match fallbacks ✅
- Golden tests (5 rows, steps traceable to source text) ✅
- Variations (count, distinctness, determinism) ✅

## Fixes Applied
- Brand token "fold" removed from standalone stripping (was breaking "folds" in normal text)
- Step extraction enhanced to handle "You can verb..." and mid-sentence "visit/contact" patterns
- Section scoring switched from RRF (tiny scores) to cosine+BM25 blend (proper [0,1] scale)

## Open Issues
None — all tests green.
