"""Cross-pair evaluation: run every query against every SIIS article (20x20 = 400 pairs).

Treat pairs with the same article title as matched.
Report the answer rate for matched vs mismatched pairs.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import TroubleshootPipeline
from app.loader import load_siis_responses


def run_cross_pair_eval():
    print("=" * 80)
    print("  CROSS-PAIR RELEVANCE GATE EVALUATION (20 x 20 = 400 PAIRS)")
    print("=" * 80)

    rows = load_siis_responses()
    pipeline = TroubleshootPipeline()
    pipeline.initialize()

    # Disable semantic cache so each cross pair is evaluated independently
    pipeline.cache.exact_map.clear()
    pipeline.cache.embeddings = None
    pipeline.cache.keys.clear()

    queries = [(r["id"], r["original_query"], r["siis_response"]["title"]) for r in rows]
    articles = [(r["id"], r["siis_response"]["title"], r["siis_response"]["content"]) for r in rows]

    total_matched = 0
    matched_answered = 0
    total_mismatched = 0
    mismatched_answered = 0

    mismatched_leak_details = []

    print("\nEvaluating 400 query-article pairs...")
    t0 = time.time()

    for q_id, q_text, q_title in queries:
        for a_id, a_title, a_content in articles:
            is_matched = (q_title == a_title)

            res = pipeline.process_query(q_text, {"title": a_title, "content": a_content})
            contexts = res.get("response", {}).get("contexts", [])
            answered = len(contexts) > 0

            if is_matched:
                total_matched += 1
                if answered:
                    matched_answered += 1
            else:
                total_mismatched += 1
                if answered:
                    mismatched_answered += 1
                    mismatched_leak_details.append({
                        "query_id": q_id,
                        "query": q_text[:60],
                        "article_id": a_id,
                        "article_title": a_title[:40],
                        "score": contexts[0].get("score", 0),
                    })

    elapsed = time.time() - t0

    matched_rate = (matched_answered / total_matched * 100) if total_matched > 0 else 0.0
    mismatched_rate = (mismatched_answered / total_mismatched * 100) if total_mismatched > 0 else 0.0

    print("\n" + "=" * 80)
    print("                     CROSS-PAIR EVALUATION RESULTS")
    print("=" * 80)
    print(f"Total Evaluated Pairs:       {len(queries) * len(articles)} in {elapsed:.2f}s")
    print(f"Matched Pairs Count:         {total_matched}")
    print(f"  Matched Answered:          {matched_answered} / {total_matched} ({matched_rate:.1f}%)")
    print(f"Mismatched Pairs Count:      {total_mismatched}")
    print(f"  Mismatched Answered:       {mismatched_answered} / {total_mismatched} ({mismatched_rate:.1f}%)")
    print(f"  Relevance Gate Rejection:  {total_mismatched - mismatched_answered} / {total_mismatched} ({(100.0 - mismatched_rate):.1f}%)")
    print("=" * 80)

    if mismatched_leak_details:
        print(f"\nMismatched pairs that returned answers ({len(mismatched_leak_details)}):")
        for item in mismatched_leak_details:
            print(f"  Query [{item['query_id']}] -> Article [{item['article_id']}] '{item['article_title']}' (Score: {item['score']})")
    else:
        print("\nPerfect gate rejection: 0 mismatched pairs produced an answer!")

    return {
        "total_pairs": len(queries) * len(articles),
        "total_matched": total_matched,
        "matched_answered": matched_answered,
        "matched_answer_rate": round(matched_rate, 2),
        "total_mismatched": total_mismatched,
        "mismatched_answered": mismatched_answered,
        "mismatched_answer_rate": round(mismatched_rate, 2),
        "gate_rejection_rate": round(100.0 - mismatched_rate, 2),
    }


if __name__ == "__main__":
    run_cross_pair_eval()
