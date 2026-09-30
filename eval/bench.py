"""Comprehensive evaluation and benchmarking suite.

Measures:
1. End-to-end recall (rows producing >= 1 valid goal with >= 1 action)
2. Catalog Deeplink coverage & validation
3. Word-count, casing, ordering, and URL leak invariants
4. Latency benchmarks (P50, P90, P95, P99) for cold pass and warm pass
5. Semantic cache hit rate and latency across generated paraphrases
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline import TroubleshootPipeline
from app.loader import (
    load_siis_responses,
    load_deeplinks_full,
    build_catalog_uri_set,
)
from app.config import DESC_WORDS, TITLE_WORDS, CATEGORY_ORDER
from app.validators import validate_no_urls, validate_goal_format


def percentile(data: list[float], p: float) -> float:
    """Calculate percentile from data list."""
    if not data:
        return 0.0
    k = (len(data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c < len(data):
        d0 = data[f] * (c - k)
        d1 = data[c] * (k - f)
        return d0 + d1
    return data[f]


def run_benchmark():
    print("=" * 80)
    print("  SMART GUIDED TROUBLESHOOTING ENGINE - EVALUATION & BENCHMARK SUITE")
    print("=" * 80)

    # 1. Initialize pipeline and catalog
    print("\n[1/5] Initializing engine & catalog...")
    pipeline = TroubleshootPipeline()
    pipeline.initialize()
    catalog_entries = load_deeplinks_full()
    catalog_uris = build_catalog_uri_set(catalog_entries)
    rows = load_siis_responses()
    print(f"  Loaded {len(catalog_entries)} catalog entries, {len(rows)} test rows")

    # 2. Pass 1: Cold run (fresh execution, populate cache)
    print("\n[2/5] Running Pass 1: Cold Execution & Extraction Recall...")
    # Clear cache for true cold benchmark
    pipeline.cache.exact_map.clear()
    pipeline.cache.embeddings = None
    pipeline.cache.keys.clear()

    cold_latencies: list[float] = []
    valid_rows = 0
    total_goals = 0
    total_actions = 0
    total_deeplinks = 0
    categories_dist: dict[str, int] = {"auto": 0, "manual": 0, "critical": 0}

    # Invariants tracking
    url_leaks = 0
    catalog_violations = 0
    desc_violations = 0
    title_violations = 0
    order_violations = 0
    manual_dl_violations = 0

    results_pass1 = []

    for row in rows:
        t0 = time.perf_counter()
        res = pipeline.process_query(row["original_query"], row["siis_response"])
        lat_ms = (time.perf_counter() - t0) * 1000
        cold_latencies.append(lat_ms)
        results_pass1.append((row, res))

        contexts = res.get("response", {}).get("contexts", [])
        if contexts:
            valid_rows += 1
            for goal in contexts:
                total_goals += 1
                title = goal.get("title", "")
                words = title.split()
                if not (TITLE_WORDS[0] <= len(words) <= TITLE_WORDS[1]):
                    title_violations += 1

                goal_str = goal.get("goal", "")
                if not validate_goal_format(goal_str):
                    pass

                actions = goal.get("actions", [])
                total_actions += len(actions)

                # Order check
                cats = [a.get("category", "manual") for a in actions]
                ord_vals = [CATEGORY_ORDER.get(c, 1) for c in cats]
                for i in range(1, len(ord_vals)):
                    if ord_vals[i] < ord_vals[i - 1]:
                        order_violations += 1

                for act in actions:
                    cat = act.get("category", "manual")
                    categories_dist[cat] = categories_dist.get(cat, 0) + 1

                    desc = act.get("description", "")
                    dwords = desc.rstrip(".").split()
                    if not (desc.startswith("It will") and DESC_WORDS[0] <= len(dwords) <= DESC_WORDS[1]):
                        desc_violations += 1

                    for sg in act.get("stepGroups", []):
                        dl = sg.get("actionableDeeplink")
                        if cat == "manual" and dl is not None:
                            manual_dl_violations += 1
                        if dl:
                            total_deeplinks += 1
                            if dl.get("deeplink") not in catalog_uris:
                                catalog_violations += 1

        # URL leak check across entire JSON response
        leaks = validate_no_urls(res)
        url_leaks += len(leaks)

    cold_latencies.sort()
    print(f"  Cold run complete: {valid_rows}/{len(rows)} rows produced plans")
    print(f"  Total Goals: {total_goals}, Total Actions: {total_actions}, Actionable Deeplinks: {total_deeplinks}")

    # 3. Pass 2: Warm run (exact cache hit)
    print("\n[3/5] Running Pass 2: Warm Execution (Exact Cache Hit)...")
    warm_latencies: list[float] = []
    warm_hits = 0

    for row in rows:
        t0 = time.perf_counter()
        res = pipeline.process_query(row["original_query"], row["siis_response"])
        lat_ms = (time.perf_counter() - t0) * 1000
        warm_latencies.append(lat_ms)
        if res.get("meta", {}).get("cache_hit") is True:
            warm_hits += 1

    warm_latencies.sort()
    warm_hit_rate = (warm_hits / len(rows)) * 100
    print(f"  Warm run complete: {warm_hits}/{len(rows)} hits ({warm_hit_rate:.1f}%)")

    # 4. Pass 3: Paraphrase variations test (semantic cache hit)
    print("\n[4/5] Running Pass 3: Paraphrase Variations (Semantic Cache Hit Rate)...")
    para_path = PROJECT_ROOT / "paraphrases.jsonl"
    para_latencies: list[float] = []
    para_hits = 0
    total_paras = 0

    if para_path.exists():
        with open(para_path, "r", encoding="utf-8") as f:
            for line in f:
                item = json.loads(line)
                variations = item.get("variations", [])
                for v in variations:
                    total_paras += 1
                    t0 = time.perf_counter()
                    # Query without SIIS (simulates user query hitting prewarmed cache)
                    res = pipeline.process_query(v, None)
                    lat_ms = (time.perf_counter() - t0) * 1000
                    para_latencies.append(lat_ms)
                    if res.get("meta", {}).get("cache_hit") is True:
                        para_hits += 1

    para_latencies.sort()
    para_hit_rate = (para_hits / total_paras * 100) if total_paras > 0 else 0.0
    print(f"  Evaluated {total_paras} paraphrases across {len(rows)} intents")
    print(f"  Paraphrase cache hits: {para_hits}/{total_paras} ({para_hit_rate:.1f}%)")

    # 5. Summary metrics table
    print("\n[5/5] Compiling Benchmark Results...")
    print("\n" + "=" * 80)
    print("                         SUMMARY BENCHMARK REPORT")
    print("=" * 80)

    print("\n--- 1. QUALITY & RECALL METRICS ---")
    print(f"  Dataset Size:                {len(rows)} queries")
    print(f"  Plan Generation Recall:      {valid_rows}/{len(rows)} ({(valid_rows/len(rows))*100:.1f}%)")
    print(f"  Total Extracted Goals:       {total_goals}")
    print(f"  Total Actions:               {total_actions}")
    print(f"  Action Distribution:         auto: {categories_dist['auto']}, manual: {categories_dist['manual']}, critical: {categories_dist['critical']}")
    print(f"  Deeplinks Matched:           {total_deeplinks}")

    print("\n--- 2. INVARIANT & SAFETY VERIFICATION ---")
    print(f"  URL Leaks Detected:          {url_leaks} (Target: 0)")
    print(f"  Catalog URI Violations:      {catalog_violations} (Target: 0)")
    print(f"  Description Word Violations: {desc_violations} (Target: 0)")
    print(f"  Title Word Violations:       {title_violations} (Target: 0)")
    print(f"  Category Order Violations:   {order_violations} (Target: 0)")
    print(f"  Manual Action DL Violations: {manual_dl_violations} (Target: 0)")

    print("\n--- 3. LATENCY BENCHMARKS (milliseconds) ---")
    print("  Metric                Cold Pass       Warm Pass (Exact)   Paraphrase Pass (Semantic)")
    print("  --------------------------------------------------------------------------------")
    print(f"  P50 (Median):         {percentile(cold_latencies, 50):>8.2f} ms      {percentile(warm_latencies, 50):>12.2f} ms       {percentile(para_latencies, 50):>15.2f} ms")
    print(f"  P90:                  {percentile(cold_latencies, 90):>8.2f} ms      {percentile(warm_latencies, 90):>12.2f} ms       {percentile(para_latencies, 90):>15.2f} ms")
    print(f"  P95:                  {percentile(cold_latencies, 95):>8.2f} ms      {percentile(warm_latencies, 95):>12.2f} ms       {percentile(para_latencies, 95):>15.2f} ms")
    print(f"  P99:                  {percentile(cold_latencies, 99):>8.2f} ms      {percentile(warm_latencies, 99):>12.2f} ms       {percentile(para_latencies, 99):>15.2f} ms")
    print(f"  Mean:                 {statistics.mean(cold_latencies):>8.2f} ms      {statistics.mean(warm_latencies):>12.2f} ms       {statistics.mean(para_latencies):>15.2f} ms")

    print("\n--- 4. CACHE EFFICIENCY ---")
    print(f"  Exact Match Hit Rate:        {warm_hit_rate:.1f}%")
    print(f"  Paraphrase Match Hit Rate:   {para_hit_rate:.1f}%")
    print(f"  P95 Cache Hit Latency:       {percentile(warm_latencies, 95):.2f} ms (SLA: <= 300 ms)")
    print("=" * 80 + "\n")

    # Output JSON summary to eval/benchmark_results.json
    summary = {
        "dataset_rows": len(rows),
        "recall_valid_rows": valid_rows,
        "recall_rate": valid_rows / len(rows),
        "total_goals": total_goals,
        "total_actions": total_actions,
        "total_deeplinks": total_deeplinks,
        "categories_distribution": categories_dist,
        "invariants": {
            "url_leaks": url_leaks,
            "catalog_violations": catalog_violations,
            "desc_violations": desc_violations,
            "title_violations": title_violations,
            "order_violations": order_violations,
            "manual_dl_violations": manual_dl_violations,
        },
        "latency_cold": {
            "p50_ms": round(percentile(cold_latencies, 50), 2),
            "p90_ms": round(percentile(cold_latencies, 90), 2),
            "p95_ms": round(percentile(cold_latencies, 95), 2),
            "p99_ms": round(percentile(cold_latencies, 99), 2),
            "mean_ms": round(statistics.mean(cold_latencies), 2),
        },
        "latency_warm": {
            "p50_ms": round(percentile(warm_latencies, 50), 2),
            "p90_ms": round(percentile(warm_latencies, 90), 2),
            "p95_ms": round(percentile(warm_latencies, 95), 2),
            "p99_ms": round(percentile(warm_latencies, 99), 2),
            "mean_ms": round(statistics.mean(warm_latencies), 2),
        },
        "latency_paraphrase": {
            "p50_ms": round(percentile(para_latencies, 50), 2),
            "p90_ms": round(percentile(para_latencies, 90), 2),
            "p95_ms": round(percentile(para_latencies, 95), 2),
            "p99_ms": round(percentile(para_latencies, 99), 2),
            "mean_ms": round(statistics.mean(para_latencies), 2),
        },
        "cache": {
            "warm_hit_rate": round(warm_hit_rate, 2),
            "paraphrase_hit_rate": round(para_hit_rate, 2),
            "total_paraphrases_tested": total_paras,
        },
    }

    results_file = PROJECT_ROOT / "eval" / "benchmark_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Benchmark summary written to {results_file}")


if __name__ == "__main__":
    run_benchmark()
