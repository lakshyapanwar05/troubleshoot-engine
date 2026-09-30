# Phase 2 Report: Extraction

## What Was Built
- `app/normalize.py` — query cleaning, multi-intent split (detects `1. "..." 2. "..."` patterns), canonical query generation (brand/model stripping)
- `app/sectioner.py` — SIIS text sectioner: strips category preambles, splits on markdown headings, filters non-actionable sections (glossary, other brands, narrative)
- `app/steps.py` — core step extraction: verb-based instruction detection, compound sentence splitting, screen-chain grouping, deduplication
- `app/classify.py` — category classification using YAML keyword/regex lists (critical > manual > auto priority)
- `app/ordering.py` — stable sort action ordering (auto -> manual -> critical)

## Test Results
All 15 extraction tests passed:
- Normalize: 4/4 ✅ (enumerator stripping, multi-intent, brand removal, sentence case)
- Sectioner: 3/3 ✅ (preamble stripping, section splitting, actionable filtering on real data)
- Steps: 3/3 ✅ (instruction detection, compound splitting, real SIIS step extraction)
- Classify: 4/4 ✅ (auto/manual/critical/contact classification)
- Ordering: 1/1 ✅ (category ordering)

## Open Issues
None — extraction pipeline working correctly on real SIIS data.
