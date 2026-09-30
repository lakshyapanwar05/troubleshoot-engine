"""Benchmark unseen paraphrases against cache prewarmed from the 20 original queries only.

Measures:
1. Semantic hit rate (percentage of unseen paraphrases that hit the cache)
2. False-hit rate (percentage of hits returning another query's plan)
3. Latency percentiles (P50, P95) for:
   - Exact hit (N >= 30)
   - Semantic hit (N >= 30)
   - Cold path (N >= 30)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import numpy as np

import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline import TroubleshootPipeline
from app.loader import load_siis_responses
from app.normalize import normalize_query

# 1. Initialize pipeline and clear cache
pipeline = TroubleshootPipeline()
pipeline.initialize()
pipeline.cache.clear()

# 2. Prewarm from the 20 original queries ONLY (no variations)
siis_rows = load_siis_responses()
row_plans = {}

for row in siis_rows:
    row_id = row["id"]
    query = row["original_query"]
    siis = row["siis_response"]
    
    # Process without caching first
    res = pipeline.process_query(query, siis)
    contexts = res.get("response", {}).get("contexts", [])
    plan = {"contexts": contexts, "row_id": row_id}
    row_plans[row_id] = plan

# Now explicitly insert ONLY the 20 original canonical queries into the cache (no variations)
pipeline.cache.clear()
for row in siis_rows:
    row_id = row["id"]
    norm = normalize_query(row["original_query"])
    canonical = norm["canonical_queries"][0] if norm["canonical_queries"] else row["original_query"]
    pipeline.cache.put(canonical, row_plans[row_id], variations=None)

print(f"Cache prewarmed with {pipeline.cache.size} entries (20 original queries only)")

# Load 100 unseen paraphrases
unseen_file = PROJECT_ROOT / "eval" / "unseen_paraphrases.jsonl"
with open(unseen_file, "r", encoding="utf-8") as f:
    unseen_items = [json.loads(line) for line in f if line.strip()]

assert len(unseen_items) == 100, f"Expected 100 unseen items, got {len(unseen_items)}"

# 3. Evaluate Semantic Hit Rate & False-Hit Rate
hits = 0
correct_hits = 0
false_hits = 0
misses = 0

semantic_hit_latencies = []

for item in unseen_items:
    q_id = item["id"]
    q_text = item["query"]

    norm = normalize_query(q_text)
    canonical = norm["canonical_queries"][0] if norm["canonical_queries"] else q_text

    t0 = time.perf_counter()
    cached = pipeline.cache.get(canonical)
    lat_ms = (time.perf_counter() - t0) * 1000.0

    if cached is not None:
        hits += 1
        semantic_hit_latencies.append(lat_ms)
        cached_row_id = cached.get("row_id")
        if cached_row_id == q_id:
            correct_hits += 1
        else:
            false_hits += 1
    else:
        misses += 1

hit_rate = (hits / len(unseen_items)) * 100.0
false_hit_rate = (false_hits / hits * 100.0) if hits > 0 else 0.0
overall_false_rate = (false_hits / len(unseen_items)) * 100.0

print(f"\n--- Unseen Paraphrases (100 total) ---")
print(f"Total Hits: {hits} / 100 ({hit_rate:.1f}%)")
print(f"Correct Hits: {correct_hits} / {hits}")
print(f"False Hits: {false_hits} / {hits} (false-hit rate of hits: {false_hit_rate:.1f}%, of total: {overall_false_rate:.1f}%)")
print(f"Misses: {misses} / 100")

# 4. Latency Benchmarks (N >= 30 each)

# Exact hit latency (repeat 20 original queries 2 times -> 40 runs)
exact_latencies = []
exact_queries = [
    (normalize_query(r["original_query"])["canonical_queries"][0]
     if normalize_query(r["original_query"])["canonical_queries"]
     else r["original_query"])
    for r in siis_rows
]

for _ in range(2):
    for q in exact_queries:
        t0 = time.perf_counter()
        _ = pipeline.cache.get(q)
        lat = (time.perf_counter() - t0) * 1000.0
        exact_latencies.append(lat)

assert len(exact_latencies) >= 30, f"Need >=30 exact runs, got {len(exact_latencies)}"

# Semantic hit latency (we have len(semantic_hit_latencies), let's ensure >= 30)
if len(semantic_hit_latencies) < 30:
    # repeat through hitting queries to get >= 30 samples
    hitting_queries = [
        item["query"] for item in unseen_items
        if pipeline.cache.get(
            normalize_query(item["query"])["canonical_queries"][0]
            if normalize_query(item["query"])["canonical_queries"] else item["query"]
        ) is not None
    ]
    while len(semantic_hit_latencies) < 30:
        for q in hitting_queries:
            canonical = normalize_query(q)["canonical_queries"][0] if normalize_query(q)["canonical_queries"] else q
            t0 = time.perf_counter()
            _ = pipeline.cache.get(canonical)
            semantic_hit_latencies.append((time.perf_counter() - t0) * 1000.0)

# Cold path latency (N >= 30)
# Process queries bypassing cache directly through pipeline extraction
cold_latencies = []
# Prewarm off, clear cache for cold runs
cold_pipeline = TroubleshootPipeline()
cold_pipeline.initialize()
cold_pipeline.cache.clear()

# Run all 20 rows + 10 repeated rows = 30 cold executions
cold_candidates = siis_rows + siis_rows[:10]
for row in cold_candidates:
    cold_pipeline.cache.clear()
    t0 = time.perf_counter()
    _ = cold_pipeline.process_query(row["original_query"], row["siis_response"])
    lat = (time.perf_counter() - t0) * 1000.0
    cold_latencies.append(lat)

assert len(cold_latencies) >= 30, f"Need >= 30 cold runs, got {len(cold_latencies)}"

def stats(vals):
    arr = np.array(vals)
    return {
        "N": len(arr),
        "mean": float(np.mean(arr)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
    }

exact_stats = stats(exact_latencies)
semantic_stats = stats(semantic_hit_latencies)
cold_stats = stats(cold_latencies)

results_summary = {
    "hit_rate": hit_rate,
    "false_hit_rate": false_hit_rate,
    "overall_false_rate": overall_false_rate,
    "exact_stats": exact_stats,
    "semantic_stats": semantic_stats,
    "cold_stats": cold_stats,
}

print("\n--- Latency Percentiles (ms) ---")
print(f"Exact Hit   (N={exact_stats['N']}): P50={exact_stats['p50']:.2f}ms, P95={exact_stats['p95']:.2f}ms")
print(f"Semantic Hit(N={semantic_stats['N']}): P50={semantic_stats['p50']:.2f}ms, P95={semantic_stats['p95']:.2f}ms")
print(f"Cold Path   (N={cold_stats['N']}): P50={cold_stats['p50']:.2f}ms, P95={cold_stats['p95']:.2f}ms")

with open(PROJECT_ROOT / "reports" / "unseen_eval_results.json", "w", encoding="utf-8") as f:
    json.dump(results_summary, f, indent=2)
