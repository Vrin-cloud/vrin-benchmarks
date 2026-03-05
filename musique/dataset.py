"""Load and sample MuSiQue dataset from HuggingFace.

Dataset: bdsaglam/musique — answerable config, validation split (2,417 questions).
Each question has ~20 distractor + supporting paragraphs.  We deduplicate
paragraphs across all sampled questions so shared Wikipedia passages are
ingested only once.
"""

import hashlib
import logging
import random
from typing import Any, Dict, List, Tuple

from datasets import load_dataset

from . import config

logger = logging.getLogger(__name__)


def _paragraph_id(title: str, text: str) -> str:
    """Stable content-hash ID for deduplication across questions."""
    return hashlib.md5(f"{title}|{text}".encode()).hexdigest()


def load_musique(
    sample_size: int | None = None,
    seed: int | None = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load MuSiQue, sample questions, and deduplicate paragraphs.

    Returns:
        (paragraphs, questions) where:
        - paragraphs: unique ``[{"id", "title", "text"}, ...]``
        - questions:  ``[{"id", "question", "answer", "answer_aliases",
                          "paragraph_ids", "supporting_paragraph_ids"}, ...]``
    """
    sample_size = sample_size or config.SAMPLE_SIZE
    seed = seed or config.RANDOM_SEED

    logger.info(
        f"Loading {config.DATASET_NAME} ({config.DATASET_CONFIG}, "
        f"{config.DATASET_SPLIT}) from HuggingFace..."
    )
    ds = load_dataset(config.DATASET_NAME, config.DATASET_CONFIG, split=config.DATASET_SPLIT)
    population_size = len(ds)
    logger.info(f"Population: {population_size} questions")

    # Sample
    random.seed(seed)
    indices = random.sample(range(population_size), min(sample_size, population_size))
    sampled = ds.select(indices)
    logger.info(f"Sampled {len(sampled)} questions (seed={seed})")

    # Deduplicate paragraphs and build question list
    seen_paragraphs: Dict[str, Dict[str, str]] = {}
    questions: List[Dict[str, Any]] = []

    for row in sampled:
        q_id = row["id"]

        para_ids: List[str] = []
        supporting_ids: List[str] = []

        for para in row["paragraphs"]:
            pid = _paragraph_id(para["title"], para["paragraph_text"])
            if pid not in seen_paragraphs:
                seen_paragraphs[pid] = {
                    "id": pid,
                    "title": para["title"],
                    "text": para["paragraph_text"],
                }
            para_ids.append(pid)
            if para["is_supporting"]:
                supporting_ids.append(pid)

        questions.append({
            "id": q_id,
            "question": row["question"],
            "answer": row["answer"],
            "answer_aliases": list(row.get("answer_aliases", []) or []),
            "paragraph_ids": para_ids,
            "supporting_paragraph_ids": supporting_ids,
        })

    paragraphs = list(seen_paragraphs.values())
    logger.info(
        f"Deduplicated paragraphs: {len(paragraphs)} unique "
        f"(from {sum(len(q['paragraph_ids']) for q in questions)} total refs)"
    )
    return paragraphs, questions
