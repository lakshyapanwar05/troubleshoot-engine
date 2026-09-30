"""Run all 20 rows through the pipeline and write results.jsonl + review table."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline import get_pipeline
from app.loader import load_siis_responses


def main():
    pipeline = get_pipeline()
    pipeline.initialize()

    rows = load_siis_responses()
    results_path = PROJECT_ROOT / "results.jsonl"

    print("=" * 100)
    print(f"{'Row':>8} {'SIIS Title':40} {'Score':>6} {'#Act':>5} {'Categories':25} {'#DL':>4} {'Fallback':15}")
    print("-" * 100)

    with open(results_path, "w", encoding="utf-8") as f:
        for row in rows:
            start = time.time()
            result = pipeline.process_query(
                row["original_query"],
                row["siis_response"],
            )
            elapsed = time.time() - start

            # Write JSONL
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

            # Extract review info
            contexts = result.get("response", {}).get("contexts", [])
            fallback = result.get("meta", {}).get("fallback", "")
            siis_title = row["siis_response"]["title"][:38]

            if contexts:
                for goal in contexts:
                    actions = goal.get("actions", [])
                    cats = [a.get("category", "?") for a in actions]
                    n_dl = sum(
                        1 for a in actions
                        for sg in a.get("stepGroups", [])
                        if sg.get("actionableDeeplink")
                    )
                    print(
                        f"{row['id']:>8} {siis_title:40} "
                        f"{goal.get('score', 0):>6.2f} {len(actions):>5} "
                        f"{','.join(cats):25} {n_dl:>4} {fallback:15}"
                    )
            else:
                print(
                    f"{row['id']:>8} {siis_title:40} "
                    f"{'N/A':>6} {'0':>5} "
                    f"{'N/A':25} {'0':>4} {fallback:15}"
                )

    print("=" * 100)
    print(f"\nResults written to {results_path}")
    print(f"Cache size: {pipeline.cache.size}")


if __name__ == "__main__":
    main()
