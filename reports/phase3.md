# Phase 3 Report: Retrieval

## What Was Built
- `app/retrieval.py` — BM25 + dense embedding hybrid retrieval with RRF fusion for catalog search, and blended cosine+BM25 for section relevance scoring
- `app/deeplinks.py` — step chain to catalog deeplink matching with verb-to-originalType priors, dummy fallback, verbatim validation copying
- Relevance gate using cosine similarity + BM25 blend (scores on [0,1] scale)

## Key Design Decisions
- Section scoring uses **0.7×cosine + 0.3×BM25** blend instead of RRF because RRF produces scores on a ~0.03 scale incompatible with REL_THRESHOLD=0.20
- Verb-to-type priors: navigate/open→onClickURL, enable→onURL, disable→offURL, adjust→updateURL
- Dummy deeplink (DL-DUMMY) used only for settings screens with no catalog match

## Test Results
All tests pass including catalog membership, URL leak scan, and golden step traceability.

## Open Issues
None.
