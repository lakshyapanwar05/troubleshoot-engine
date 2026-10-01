# Smart Guided Troubleshooting Engine

A rule-based, offline-first Python backend that converts customer complaints and raw technical support documentation into machine-actionable troubleshooting plans with verifiable settings deeplinks.

> **Core Design Principle:**
> **Rules decide, ML only ranks, an LLM never decides.**
> There is no LLM at request time. This eliminates token costs, latency spikes, and hallucinations by construction. Every step is traceable to authoritative documentation, and every deeplink is copied verbatim from a pre-validated catalog.

---

## Run locally (Python 3.11)

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
uvicorn app.main:app --port 8000
```

Then open http://localhost:8000 (Frontend UI) or http://localhost:8000/docs (API documentation).

---

## Key Capabilities & Invariants

1. **Zero URL Leaks**: String-level regex scanning scrubs and rejects any unauthorized external URLs, raw web links, or protocol leaks.
2. **Verbatim Catalog Integrity**: Actionable settings deeplinks (`voiceassist://...`) and validation rules are strictly sourced and validated against the 578-entry deeplink catalog.
3. **Deterministic Output**: Identical queries and SIIS documents always produce identical JSON outputs.
4. **Two-Tier Semantic Caching**:
   - **Tier 1 (Exact Match)**: Normalized string dictionary lookup (< 1 ms latency).
   - **Tier 2 (Vectorized Cosine Similarity)**: Pre-indexed query embeddings using offline MiniLM-L6-v2 (`>= 0.92` cosine similarity threshold).
   - **Paraphrase Indexing**: Automatically generates and indexes 8–10 linguistic variations (formal, casual, typo, keyword, frustrated) per intent.
5. **Strict Text Rules**:
   - **Action Descriptions**: Exactly 5–7 words, strictly beginning with `"It will"`.
   - **Action Titles**: Exactly 2–3 words in sentence case.
   - **Goals**: Strict template compliance (`Follow these steps to perform this <Symptom> <Troubleshooting|Configuration>`).
   - **Category Ordering**: Actions are strictly sorted: `auto` → `manual` → `critical` (critical actions always last).
   - **Manual Actions**: Guaranteed to contain no actionable deeplinks (`actionableDeeplink: null`).

---

## Architectural Pipeline

```
                           Raw Customer Query + Optional SIIS Text
                                             │
                                             ▼
                               [1. Query Normalization]
                       • Strip enumerations & quote marks
                       • Brand removal (Nexa, TechCorp)
                       • Multi-intent splitting (max 3 intents)
                                             │
                                             ▼
                              [2. Markdown & Sectioning]
                       • Strip SIIS metadata preambles
                       • Split by markdown headers (# / ## / ###)
                       • Filter out non-actionable sections
                                             │
                                             ▼
                             [3. Hybrid Relevance Gate]
                       • 0.7 * Cosine Similarity + 0.3 * BM25
                       • Non-negative BM25 Okapi clipping
                       • Threshold: REL_THRESHOLD >= 0.20
                                             │
                                             ▼
                              [4. Step Extraction & Chains]
                       • Imperative verb detection (tap, turn on, etc.)
                       • Compound instruction splitting ("and then")
                       • Screen-chain grouping (Settings > Display > ...)
                                             │
                                             ▼
                              [5. YAML Rule Classification]
                       • categories.yaml + verbs.yaml
                       • Priority: Critical (3) > Manual (2) > Auto (1)
                       • Contact/visit forced to manual
                                             │
                                             ▼
                             [6. Catalog Deeplink Matching]
                       • Hybrid BM25 + dense retrieval over catalog
                       • Verb-to-originalType priors (onClick, on, off, update)
                       • Settings fallback: DL-DUMMY
                                             │
                                             ▼
                            [7. Stable Action Ordering]
                       • auto (0) → manual (1) → critical (2)
                                             │
                                             ▼
                              [8. Final Gate Validation]
                       • URL scrubbing & recursive safety scan
                       • Catalog URI membership check
                       • Word count & casing formatting
                                             │
                                             ▼
                           Validated Machine-Actionable Plan
```

---

## Project Structure

```
troubleshoot-engine/
├── app/                        # Core backend modules
│   ├── cache.py                # Two-tier semantic cache (exact + cosine)
│   ├── classify.py             # Action classification (auto/manual/critical)
│   ├── config.py               # Constants, thresholds, and paths
│   ├── deeplinks.py            # Catalog retriever & verb-to-type priors
│   ├── envelope.py             # Request/response envelope models
│   ├── llm_optional.py         # Optional Ollama offline stub (disabled by default)
│   ├── loader.py               # Data loaders (catalog, SIIS, input queries)
│   ├── main.py                 # FastAPI application with async lifespan
│   ├── normalize.py            # Query cleaning, multi-intent split, canonicalization
│   ├── ordering.py             # Action ordering (auto -> manual -> critical)
│   ├── pipeline.py             # Master pipeline orchestrator
│   ├── retrieval.py            # BM25 + dense embedding hybrid search
│   ├── sectioner.py            # SIIS markdown section parser
│   ├── steps.py                # Imperative instruction extractor
│   ├── textrules.py            # Strict word-count & casing formatters
│   ├── validators.py           # Final validation gate & URL leak scanner
│   └── variations.py           # Deterministic 8-10 paraphrase generator
├── cache/                      # Persisted cache artifacts
│   ├── cache_index.json        # Serialized plan store & key mapping
│   ├── cache_vectors.npy       # Precomputed embedding matrix
│   └── catalog_emb.npy         # Precomputed catalog embeddings
├── data/                       # Ground-truth datasets
│   ├── deeplinks.json          # 578 actionable & validation settings deeplinks
│   ├── input.txt               # 20 customer queries
│   ├── sample_output.json      # Target response format reference
│   └── siis_responses.json     # 20 raw support documentation articles
├── eval/                       # Benchmark and evaluation suite
│   ├── bench.py                # Comprehensive latency, recall, and cache benchmark
│   └── benchmark_results.json  # Recorded benchmark metrics
├── models/
│   └── minilm/                 # Local all-MiniLM-L6-v2 embedding model (offline)
├── reports/                    # Phase build and verification reports (1 to 6)
├── rules/                      # Declarative rule definitions
│   ├── categories.yaml         # Category matching keywords
│   ├── symptoms.yaml           # Symptom ontology and goal mappings
│   ├── synonyms.yaml           # Domain synonyms for query variations
│   └── verbs.yaml              # Imperative verb priors
├── scripts/                    # Automation scripts
│   ├── generate_paraphrases.py # Generate paraphrases.jsonl
│   ├── prewarm.py              # Cache prewarming script
│   └── run_batch.py            # Batch execution over all 20 rows
├── tests/
│   └── test_engine.py          # 54 comprehensive unit, golden, and integration tests
├── Dockerfile                  # Container definition
├── requirements.txt            # Python dependencies
├── results.jsonl               # Processed results for all 20 dataset rows
├── paraphrases.jsonl           # 198 generated query variations
└── schema.py                   # Immutable Pydantic v2 data contract
```

---

## Setup & Installation

### Prerequisites
- Python 3.11+
- Virtual environment (`venv`)

### 1. Environment Setup
```bash
# Clone or navigate to the workspace
cd troubleshoot-engine

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
```

### 2. Verify Models and Setup
The repository bundles the `sentence-transformers/all-MiniLM-L6-v2` weights locally under `models/minilm/`.
```bash
python check_setup.py
```

### 3. Prewarm Cache
Populate the semantic cache with all 20 reference queries and their paraphrases:
```bash
python scripts/prewarm.py
```

---

## Running the API

Start the FastAPI production server via Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Once running:
- **Interactive Web UI:** http://localhost:8000 (served statically from `frontend/TroubleShoot`)
- **Interactive Swagger Docs:** http://localhost:8000/docs
- **ReDoc Documentation:** http://localhost:8000/redoc

### Endpoints

#### 1. Health Check
```http
GET /health
```
**Response:**
```json
{"status": "ok"}
```
*(Returns 503 while the engine is loading models and initializing the catalog).*

#### 2. Troubleshooting Engine
```http
POST /v1/troubleshoot
Content-Type: application/json

{
  "query": "My screen went completely black after about a month of use.",
  "siis_response": {
    "title": "Blank or black display on a smartphone",
    "content": "## Step 1: Force restart your phone\nPress and hold the Volume down and Power keys simultaneously for at least 7 seconds until the phone restarts."
  }
}
```

**Response conforming to `schema.py`:**
```json
{
  "query": "My screen went completely black after about a month of use.",
  "query_variations": [
    "I would like to report that my screen went completely black...",
    "hey my screen went completely black...",
    "screen went completely black month use"
  ],
  "response": {
    "contexts": [
      {
        "goal": "Follow these steps to perform this Blank Display Troubleshooting",
        "title": "Blank display issue",
        "score": 0.38,
        "actions": [
          {
            "actionName": "Force Restart Your Phone",
            "description": "It will reboot the device completely.",
            "stepGroups": [
              {
                "steps": [
                  "Press and hold the Volume down and Power keys simultaneously for at least 7 seconds until the phone restarts."
                ],
                "actionableDeeplink": null,
                "validationDeeplink": null
              }
            ],
            "category": "manual"
          }
        ]
      }
    ]
  },
  "meta": {
    "latency_ms": 1,
    "cache_hit": true,
    "model": "rules-v1",
    "cost_usd": 0.0
  }
}
```

---

## Testing & Verification

### Running the Test Suite
The test suite consists of 54 tests covering foundation components, extraction logic, validators, URL leak scanners, golden step traceability, and variation generation:
```bash
pytest -v
```

### Running Batch Processing
Processes all 20 dataset rows and writes `results.jsonl`:
```bash
python scripts/run_batch.py
```

### Running Benchmarks
Executes the evaluation benchmark suite measuring cold pass recall, warm pass latency, and semantic cache hit rate across all 198 generated paraphrases:
```bash
python eval/bench.py
```

---

## Evaluation & Benchmark Results

Measured on 20 customer support cases and 198 query variations:

| Metric | Result | Target / SLA | Status |
| :--- | :---: | :---: | :---: |
| **Plan Generation Recall** | **20 / 20 (100.0%)** | >= 90% | **PASSED** |
| **Total Extracted Goals** | **22 Goals** | >= 20 | **PASSED** |
| **Total Actions Generated** | **80 Actions** | - | **PASSED** |
| **Action Distribution** | auto: 10, manual: 51, critical: 19 | - | **PASSED** |
| **Action Ordering Invariant** | **0 Violations** (auto → manual → critical) | 0 | **PASSED** |
| **URL Leak Violations** | **0 Violations** across all responses | 0 | **PASSED** |
| **Catalog URI Violations** | **0 Violations** (100% in catalog) | 0 | **PASSED** |
| **Description Word Limits** | **0 Violations** (5–7 words, "It will...") | 0 | **PASSED** |
| **Title Word Limits** | **0 Violations** (2–3 words sentence case) | 0 | **PASSED** |
| **Manual Action Deeplinks** | **0 Violations** (all `null`) | 0 | **PASSED** |
| **Exact Match Cache Hit Rate** | **100.0%** | >= 95% | **PASSED** |
| **Paraphrase Semantic Hit Rate**| **100.0%** (198/198 hits) | >= 90% | **PASSED** |
| **P50 Latency (Cold Pipeline)** | **187.88 ms** | < 1000 ms | **PASSED** |
| **P95 Latency (Cache Hit)** | **0.57 ms** | **<= 300 ms** | **PASSED** |

---

## Docker Deployment

Build and run the containerized application:

```bash
# Build the Docker image
docker build -t troubleshoot-engine .

# Run the container
docker run -d --name troubleshoot-engine -p 8000:8000 troubleshoot-engine

# Check health endpoint
curl http://localhost:8000/health
```

Google Drive Link: https://drive.google.com/drive/folders/1SYvcc2MEdlcULTHq7U0Rzvu6AInxT6KC?usp=drive_link
