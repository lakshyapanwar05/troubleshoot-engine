"""Prewarm the cache with all 20 rows."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline import get_pipeline
from app.loader import load_siis_responses


def main():
    pipeline = get_pipeline()
    pipeline.initialize()

    rows = load_siis_responses()
    pipeline.prewarm(rows)
    print(f"Cache prewarmed with {pipeline.cache.size} entries")


if __name__ == "__main__":
    main()
