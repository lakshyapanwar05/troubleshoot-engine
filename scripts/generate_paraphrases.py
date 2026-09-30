"""Generate paraphrases for all 20 rows and write to paraphrases.jsonl."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.loader import load_siis_responses
from app.normalize import normalize_query
from app.variations import generate_variations


def main():
    rows = load_siis_responses()
    output_path = PROJECT_ROOT / "paraphrases.jsonl"

    print(f"Generating paraphrases for {len(rows)} queries...")
    total_variations = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for row in rows:
            query = row["original_query"]
            norm = normalize_query(query)
            canonical = norm["canonical_queries"][0] if norm["canonical_queries"] else query
            variations = generate_variations(canonical)

            entry = {
                "id": row["id"],
                "query": query,
                "canonical_query": canonical,
                "variations_count": len(variations),
                "variations": variations,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            total_variations += len(variations)
            print(f"  {row['id']}: generated {len(variations)} variations")

    print(f"\nWrote {len(rows)} entries with {total_variations} total variations to {output_path}")


if __name__ == "__main__":
    main()
