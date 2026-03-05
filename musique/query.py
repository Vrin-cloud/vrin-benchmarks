"""Run MuSiQue queries against VRIN and extract short answers.

Each question is sent to VRIN; the verbose response is then passed through
GPT-4o-mini to extract a short factoid answer suitable for EM/F1 scoring.
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from tqdm import tqdm
from vrin import VRINClient

from . import config
from .evaluate import evaluate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Answer extraction prompt (factoid-only — MuSiQue answers are short spans)
# ---------------------------------------------------------------------------
_EXTRACTION_PROMPT = """\
Extract the shortest possible factual answer to this question from the response below.

Question: {question}

Response:
{response}

Rules:
- Return ONLY the bare answer: a name, number, date, or minimal phrase (1-5 words max)
- Strip titles, honorifics, and parenthetical info: "Boris Yeltsin" → "Yeltsin", "Treaty of Paris (1783)" → "Treaty of Paris", "November 2005" → "2005", "Major General Sir Edward Pakenham" → "Edward Pakenham"
- If the response names multiple entities, pick the one that directly answers the question
- The response may hedge ("the documents do not state...", "I couldn't find...") but still contain the answer — extract it anyway
- ONLY return "Insufficient information" if the response truly contains zero factual answer to the question

Answer:"""


def extract_short_answer(
    question: str,
    vrin_summary: str,
    openai_api_key: str | None = None,
) -> str:
    """Use GPT-4o-mini to pull a short answer span from VRIN's verbose response."""
    api_key = openai_api_key or config.OPENAI_API_KEY
    if not api_key:
        # No OpenAI key — return truncated response as best effort
        return vrin_summary[:200].strip()

    prompt = _EXTRACTION_PROMPT.format(
        question=question,
        response=vrin_summary[:4000],
    )

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.ANSWER_EXTRACTOR_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": config.ANSWER_EXTRACTOR_MAX_TOKENS,
                "temperature": config.ANSWER_EXTRACTOR_TEMPERATURE,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        logger.warning(f"OpenAI returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Answer extraction failed: {e}")

    return vrin_summary[:200].strip()


# ---------------------------------------------------------------------------
# Single-question runner
# ---------------------------------------------------------------------------


def _query_one(
    client: VRINClient,
    question: Dict[str, Any],
    query_depth: Optional[str],
    openai_key: str | None,
) -> Dict[str, Any]:
    """Query VRIN for one question and extract short answer."""
    start = time.time()
    try:
        kwargs: Dict[str, Any] = {"response_mode": "chat"}
        if query_depth is not None:
            kwargs["query_depth"] = query_depth

        result = client.query(question["question"], stream=False, **kwargs)
        latency_ms = round((time.time() - start) * 1000)

        vrin_summary = result.get("summary", result.get("response", ""))
        insufficient = result.get("insufficient_coverage", False)
        metadata = result.get("metadata", {})

        # Extract short answer
        if insufficient:
            extracted = "Insufficient information"
        elif vrin_summary:
            extracted = extract_short_answer(
                question["question"], vrin_summary, openai_key
            )
        else:
            extracted = ""

        return {
            "question_id": question["id"],
            "question": question["question"],
            "gold_answer": question["answer"],
            "gold_aliases": question.get("answer_aliases", []),
            "vrin_summary": vrin_summary,
            "extracted_answer": extracted,
            "vrin_facts_count": result.get(
                "total_facts", metadata.get("total_facts", 0)
            ),
            "vrin_chunks_count": result.get(
                "total_chunks", metadata.get("total_chunks", 0)
            ),
            "insufficient_coverage": insufficient,
            "latency_ms": latency_ms,
            "auto_complexity": metadata.get(
                "query_complexity", metadata.get("auto_complexity", "")
            ),
            "status": "completed",
        }
    except Exception as e:
        logger.warning(f"Query failed for {question['id']}: {e}")
        return {
            "question_id": question["id"],
            "question": question["question"],
            "gold_answer": question["answer"],
            "gold_aliases": question.get("answer_aliases", []),
            "vrin_summary": "",
            "extracted_answer": "",
            "vrin_facts_count": 0,
            "vrin_chunks_count": 0,
            "insufficient_coverage": False,
            "latency_ms": round((time.time() - start) * 1000),
            "auto_complexity": "",
            "status": "failed",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Batch query runner
# ---------------------------------------------------------------------------


def _save_results(results: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(results, f, indent=2)
    tmp.rename(path)


def run_queries(
    client: VRINClient,
    questions: List[Dict[str, Any]],
    results_dir: Path | None = None,
    query_depth: Optional[str] = None,
    concurrency: int | None = None,
) -> List[Dict[str, Any]]:
    """Run all queries with concurrency and resumability.

    Returns:
        List of per-question result dicts.
    """
    results_dir = results_dir or config.RESULTS_DIR
    concurrency = concurrency or config.QUERY_CONCURRENCY
    results_file = results_dir / "query_results.json"

    # Load existing results for resumability
    existing: Dict[str, Dict[str, Any]] = {}
    if results_file.exists():
        with open(results_file) as f:
            for rec in json.load(f):
                if rec.get("status") == "completed":
                    existing[rec["question_id"]] = rec

    remaining = [q for q in questions if q["id"] not in existing]
    logger.info(
        f"Queries: {len(questions)} total, "
        f"{len(existing)} already done, {len(remaining)} remaining"
    )

    results: List[Dict[str, Any]] = list(existing.values())

    if not remaining:
        logger.info("All queries already completed — nothing to do")
        return results

    openai_key = config.OPENAI_API_KEY
    save_counter = 0

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_query_one, client, q, query_depth, openai_key): q["id"]
            for q in remaining
        }

        for future in tqdm(
            as_completed(futures), total=len(futures), desc="Querying"
        ):
            rec = future.result()
            results.append(rec)
            save_counter += 1
            # Checkpoint every 10 — save and print interim metrics
            if save_counter % 10 == 0:
                _save_results(results, results_file)
                _print_checkpoint_metrics(results, save_counter, len(futures))

    _save_results(results, results_file)

    completed = sum(1 for r in results if r.get("status") == "completed")
    failed = sum(1 for r in results if r.get("status") == "failed")
    logger.info(f"Queries complete: {completed} succeeded, {failed} failed")
    return results


def _print_checkpoint_metrics(
    results: List[Dict[str, Any]], done: int, total: int
) -> None:
    """Print interim EM/F1 metrics at query checkpoints."""
    try:
        metrics = evaluate(results)
        if "error" in metrics:
            return
        logger.info(
            f"--- Checkpoint {done}/{total} --- "
            f"EM={metrics['exact_match']:.3f}  "
            f"F1={metrics['token_f1']:.3f}  "
            f"Insuff={metrics['insufficient_coverage_rate']}%  "
            f"AvgLatency={metrics['avg_latency_ms']}ms  "
            f"AvgFacts={metrics['avg_facts_retrieved']}  "
            f"AvgChunks={metrics['avg_chunks_retrieved']}"
        )
        if metrics.get("by_complexity"):
            for cx, data in metrics["by_complexity"].items():
                logger.info(
                    f"  [{cx}] EM={data['exact_match']:.3f}  "
                    f"F1={data['token_f1']:.3f}  (N={data['n']})"
                )
    except Exception as e:
        logger.warning(f"Checkpoint metrics failed: {e}")
