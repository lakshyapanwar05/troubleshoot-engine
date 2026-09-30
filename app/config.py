"""Central configuration — every threshold, path, and feature flag lives here."""
from pathlib import Path
import os

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RULES_DIR = PROJECT_ROOT / "rules"
CACHE_DIR = PROJECT_ROOT / "cache"
MODELS_DIR = PROJECT_ROOT / "models"

DEEPLINKS_PATH = DATA_DIR / "deeplinks.json"
SIIS_PATH = DATA_DIR / "siis_responses.json"
INPUT_PATH = DATA_DIR / "input.txt"

# Embedding model — local path first, fallback to HF name (never used at runtime)
EMBEDDING_MODEL_PATH = str(MODELS_DIR / "minilm")
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL", EMBEDDING_MODEL_PATH
)

# ── Text-rule constants ────────────────────────────────────────────────
DESC_WORDS: tuple[int, int] = (5, 7)          # action description word range
TITLE_WORDS: tuple[int, int] = (2, 3)         # title word range
MAX_ACTIONS_PER_GOAL: int = 6                 # cap on actions per goal
MAX_GOALS: int = 3                            # cap on sub-queries / goals

# ── Retrieval thresholds (tunable) ─────────────────────────────────────
REL_THRESHOLD: float = float(os.getenv("REL_THRESHOLD", "0.35"))
DL_THRESHOLD: float = float(os.getenv("DL_THRESHOLD", "0.25"))
CACHE_THRESHOLD: float = float(os.getenv("CACHE_THRESHOLD", "0.75"))

# ── RRF parameter ─────────────────────────────────────────────────────
RRF_K: int = 60  # reciprocal rank fusion constant

# ── Feature flags ──────────────────────────────────────────────────────
USE_LLM: bool = os.getenv("USE_LLM", "false").lower() == "true"

# ── Brand / model tokens to strip from queries ────────────────────────
BRAND_TOKENS: set[str] = {
    "techcorp", "nexa", "x1", "ultra", "a14", "a15", "a15g",
    "samsung", "galaxy", "iphone", "apple",
}
# Regex for brand+model patterns — 'fold' only after brand name
BRAND_MODEL_PATTERN = r"\b(?:techcorp|nexa|(?:nexa\s+)?fold|x1|ultra|a1[45]g?|a14/a15)\b"

# ── Goal template ─────────────────────────────────────────────────────
GOAL_TROUBLESHOOTING = "Follow these steps to perform this {topic} Troubleshooting"
GOAL_CONFIGURATION = "Follow these steps to perform this {topic} Configuration"

# ── Category ordering (lower = earlier) ───────────────────────────────
CATEGORY_ORDER = {"auto": 0, "manual": 1, "critical": 2}

# ── Cache persistence paths ───────────────────────────────────────────
CATALOG_EMB_PATH = CACHE_DIR / "catalog_emb.npy"
CACHE_VECTORS_PATH = CACHE_DIR / "cache_vectors.npy"
CACHE_INDEX_PATH = CACHE_DIR / "cache_index.json"
