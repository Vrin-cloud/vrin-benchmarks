"""Configuration for MuSiQue benchmark."""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
VRIN_API_KEY: str = os.environ.get("VRIN_API_KEY", "")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
DATASET_NAME = "bdsaglam/musique"
DATASET_CONFIG = "answerable"
DATASET_SPLIT = "validation"

# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
SAMPLE_SIZE = 300
RANDOM_SEED = 42

# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------
QUERY_DEPTH: str | None = None  # None = test v32 auto-routing
QUERY_CONCURRENCY = 5

# ---------------------------------------------------------------------------
# Ingestion — Gradient2 adaptive concurrency
# ---------------------------------------------------------------------------
INGEST_CONCURRENCY = 4            # initial concurrent workers
INGEST_MAX_CONCURRENCY = 12       # ceiling for adaptive limiter
INGEST_MIN_CONCURRENCY = 1        # floor (serialize under extreme contention)
GRADIENT2_SMOOTHING = 0.2         # limit update smoothing (80% old estimate retained)
GRADIENT2_TOLERANCE = 2.0         # RTT tolerance before reducing (higher = more lenient)
GRADIENT2_LONG_WINDOW = 100       # samples for baseline RTT EWMA

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# Answer extraction (GPT-4o-mini — same as MultiHopRAG benchmark)
# ---------------------------------------------------------------------------
ANSWER_EXTRACTOR_MODEL = "gpt-4o-mini"
ANSWER_EXTRACTOR_MAX_TOKENS = 50
ANSWER_EXTRACTOR_TEMPERATURE = 0
