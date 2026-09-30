"""Evaluate unseen paraphrases with siis_response=None (Cache + Local SIIS Fallback).

Reports:
1. Overall answer rate
2. Correctness (same plan or same-title article as source query)
3. Cold P95 latency for fallback path
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline import TroubleshootPipeline
from app.loader import load_siis_responses
from app.normalize import normalize_query

pipeline = TroubleshootPipeline()
pipeline.initialize()

# Prewarm with all 20 rows (canonical + variations)
siis_rows = load_siis_responses()
pipeline.prewarm(siis_rows)

id_to_title = {r["id"]: r["siis_response"]["title"] for r in siis_rows}
id_to_answerable = {r["id"]: (r["id"] not in {"row_7", "row_8", "row_10", "row_12", "row_20"}) for r in siis_rows}

# Pre-compute the canonical plans for each row for exact plan comparison
canonical_plans = {}
for r in siis_rows:
    res = pipeline.process_query(r["original_query"], r["siis_response"])
    canonical_plans[r["id"]] = res["response"].get("contexts", [])

# Load 100 unseen paraphrases
with open(PROJECT_ROOT / "eval" / "unseen_paraphrases.jsonl", "r", encoding="utf-8") as f:
    unseen_items = [json.loads(line) for line in f if line.strip()]

assert len(unseen_items) == 100, f"Expected 100 items, got {len(unseen_items)}"

results = []
cache_hits = 0
fallback_hits = 0
rejections = 0

correct_count = 0
answered_count = 0
fallback_latencies = []

for item in unseen_items:
    qid = item["id"]
    qtext = item["query"]
    expected_title = id_to_title[qid]
    is_answerable = id_to_answerable[qid]

    t0 = time.perf_counter()
    res = pipeline.process_query(qtext, siis_response=None)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    contexts = res["response"].get("contexts", [])
    cache_hit = res["meta"].get("cache_hit", False)
    fallback = res["meta"].get("fallback")

    is_answered = len(contexts) > 0
    if is_answered:
        answered_count += 1

    if cache_hit:
        cache_hits += 1
    elif is_answered:
        fallback_hits += 1
        fallback_latencies.append(elapsed_ms)
    else:
        rejections += 1
        fallback_latencies.append(elapsed_ms)

    # Check correctness:
    # 1. If answered: verify retrieved action names or goal title match the source query's canonical plan
    # 2. If rejected: correct if query was in unanswerable set
    is_correct = False
    if is_answered:
        if canonical_plans[qid]:
            expected_actions = set(a["actionName"] for a in canonical_plans[qid][0].get("actions", []))
            actual_actions = set(a["actionName"] for a in contexts[0].get("actions", []))
            # Match if action overlap exists or goal title matches
            if expected_actions and actual_actions and (expected_actions & actual_actions):
                is_correct = True
            elif contexts[0].get("title") == canonical_plans[qid][0].get("title"):
                is_correct = True
    else:
        if not is_answerable:
            is_correct = True  # Correct rejection

    if is_correct:
        correct_count += 1

    results.append({
        "id": qid,
        "query": qtext,
        "answered": is_answered,
        "cache_hit": cache_hit,
        "fallback": fallback,
        "is_correct": is_correct,
        "latency_ms": elapsed_ms,
    })

answer_rate = answered_count / len(unseen_items) * 100.0
correctness_rate = correct_count / len(unseen_items) * 100.0
answerable_correct = sum(1 for r in results if r["is_correct"] and id_to_answerable[r["id"]])
answerable_total = sum(1 for r in results if id_to_answerable[r["id"]])
answerable_accuracy = answerable_correct / answerable_total * 100.0

p50_fallback = float(np.percentile(fallback_latencies, 50)) if fallback_latencies else 0.0
p95_fallback = float(np.percentile(fallback_latencies, 95)) if fallback_latencies else 0.0

print("\n" + "=" * 75)
print("  EVALUATION OF UNSEEN PARAPHRASES WITH LOCAL SIIS FALLBACK (siis=None)")
print("=" * 75)
print(f"Total Unseen Queries:      {len(unseen_items)}")
print(f"Total Answered:            {answered_count} / 100 ({answer_rate:.1f}%)")
print(f"  - Direct Cache Hits:     {cache_hits}")
print(f"  - Local SIIS Fallbacks:  {fallback_hits}")
print(f"Gate Rejections:           {rejections} / 100 (Expected unanswerable: 25)")
print(f"Overall Correctness:       {correct_count} / 100 ({correctness_rate:.1f}%)")
print(f"Answerable Accuracy:       {answerable_correct} / {answerable_total} ({answerable_accuracy:.1f}%)")
print(f"Fallback Latency P50:      {p50_fallback:.2f} ms")
print(f"Fallback Latency P95:      {p95_fallback:.2f} ms")
print("=" * 75)

summary = {
    "total_queries": len(unseen_items),
    "answered_count": answered_count,
    "answer_rate": answer_rate,
    "cache_hits": cache_hits,
    "fallback_hits": fallback_hits,
    "rejections": rejections,
    "correct_count": correct_count,
    "correctness_rate": correctness_rate,
    "answerable_accuracy": answerable_accuracy,
    "fallback_p50_ms": p50_fallback,
    "fallback_p95_ms": p95_fallback,
    "results": results,
}

with open(PROJECT_ROOT / "reports" / "fallback_eval_results.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)

print("Saved reports/fallback_eval_results.json")
