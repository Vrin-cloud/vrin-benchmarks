"""Bulk-ingest MuSiQue paragraphs into VRIN.

Uses ThreadPoolExecutor gated by a Gradient2 adaptive concurrency limiter.
The limiter monitors per-paragraph RTT and adjusts concurrency proactively —
reducing workers when Neptune latency rises (congestion forming) and
increasing when latency is stable.

Progress is saved to ``results/ingest_progress.json`` so interrupted
runs can be resumed.
"""

import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

from tqdm import tqdm
from vrin import VRINClient

from . import config
from .adaptive_concurrency import Gradient2Limiter

logger = logging.getLogger(__name__)

# Progress save interval (every N completions)
_SAVE_INTERVAL = 10

# Stats logging interval (every N completions)
_STATS_INTERVAL = 50


def _load_progress(path: Path) -> Dict[str, Any]:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _save_progress(progress: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(progress, f, indent=2)
    tmp.rename(path)


def _ingest_one(client: VRINClient, para: Dict[str, str]) -> Dict[str, Any]:
    """Insert a single paragraph; returns a progress record."""
    start = time.time()
    try:
        result = client.insert(
            para["text"],
            title=para["title"],
            tags=["musique-benchmark"],
            wait=True,
            max_wait=180.0,
        )
        return {
            "id": para["id"],
            "status": "completed",
            "facts_extracted": result.get("facts_extracted", 0),
            "facts_stored": result.get("facts_stored", 0),
            "job_id": result.get("job_id", ""),
            "elapsed_s": round(time.time() - start, 1),
        }
    except Exception as e:
        logger.warning(f"Insert failed for {para['id']}: {e}")
        return {
            "id": para["id"],
            "status": "failed",
            "error": str(e),
            "elapsed_s": round(time.time() - start, 1),
        }


def _ingest_one_adaptive(
    client: VRINClient,
    para: Dict[str, str],
    limiter: Gradient2Limiter,
) -> Dict[str, Any]:
    """Acquire a limiter slot, ingest, and report RTT back to the limiter."""
    with limiter.acquire() as token:
        start = time.monotonic()
        result = _ingest_one(client, para)
        elapsed = time.monotonic() - start
        dropped = result["status"] == "failed"
        token.report(rtt=elapsed, dropped=dropped)
    return result


def ingest_paragraphs(
    client: VRINClient,
    paragraphs: List[Dict[str, str]],
    results_dir: Path | None = None,
    concurrency: int | None = None,
) -> Dict[str, Any]:
    """Ingest paragraphs with Gradient2 adaptive concurrency and resumability.

    The Gradient2 limiter gates how many paragraphs are processed
    concurrently. It starts at ``concurrency`` (default 4) and adapts
    based on observed latency — proactively reducing before 429 errors.

    Returns:
        Full progress dict keyed by paragraph ID.
    """
    results_dir = results_dir or config.RESULTS_DIR
    initial_concurrency = concurrency or config.INGEST_CONCURRENCY
    progress_file = results_dir / "ingest_progress.json"

    progress = _load_progress(progress_file)
    completed_ids = {
        pid for pid, rec in progress.items() if rec.get("status") == "completed"
    }
    remaining = [p for p in paragraphs if p["id"] not in completed_ids]

    logger.info(
        f"Ingestion: {len(paragraphs)} total, "
        f"{len(completed_ids)} already done, {len(remaining)} remaining"
    )

    if not remaining:
        logger.info("All paragraphs already ingested — nothing to do")
        return progress

    # Gradient2 adaptive limiter
    limiter = Gradient2Limiter(
        initial_limit=initial_concurrency,
        min_limit=config.INGEST_MIN_CONCURRENCY,
        max_limit=config.INGEST_MAX_CONCURRENCY,
        smoothing=config.GRADIENT2_SMOOTHING,
        tolerance=config.GRADIENT2_TOLERANCE,
        long_window=config.GRADIENT2_LONG_WINDOW,
    )

    logger.info(
        f"Gradient2 limiter: initial={initial_concurrency}, "
        f"min={config.INGEST_MIN_CONCURRENCY}, max={config.INGEST_MAX_CONCURRENCY}, "
        f"smoothing={config.GRADIENT2_SMOOTHING}, tolerance={config.GRADIENT2_TOLERANCE}"
    )

    total_done = 0
    total_failed = 0
    ingestion_start = time.time()
    save_counter = 0

    # ThreadPoolExecutor max_workers is the ceiling; the limiter gates actual concurrency
    with ThreadPoolExecutor(max_workers=config.INGEST_MAX_CONCURRENCY) as pool:
        futures: Dict[Future, str] = {}

        # Submit all paragraphs — limiter.acquire() inside each worker gates concurrency
        for para in remaining:
            future = pool.submit(_ingest_one_adaptive, client, para, limiter)
            futures[future] = para["id"]

        # Collect results as they complete
        pbar = tqdm(total=len(remaining), desc="Ingesting")
        for future in _as_completed_iter(futures):
            result = future.result()
            progress[result["id"]] = result

            if result["status"] == "completed":
                total_done += 1
            else:
                total_failed += 1

            save_counter += 1
            pbar.update(1)

            # Periodic progress save
            if save_counter % _SAVE_INTERVAL == 0:
                _save_progress(progress, progress_file)

            # Periodic stats logging
            if save_counter % _STATS_INTERVAL == 0:
                stats = limiter.stats
                total_elapsed = round(time.time() - ingestion_start, 1)
                rate = save_counter / total_elapsed if total_elapsed > 0 else 0
                eta = round(
                    (len(remaining) - save_counter) / rate / 60, 1
                ) if rate > 0 else 0
                logger.info(
                    f"Progress: {save_counter}/{len(remaining)} "
                    f"({total_done} ok, {total_failed} fail) | "
                    f"Limiter: limit={stats['current_limit']}, "
                    f"long_rtt={stats['long_rtt']:.1f}s, "
                    f"drops={stats['drops_total']} | "
                    f"Rate: {rate:.2f} para/s, ETA ~{eta} min"
                )

        pbar.close()

    # Final save
    _save_progress(progress, progress_file)

    # Final stats
    total_elapsed = round(time.time() - ingestion_start, 1)
    total_facts = sum(r.get("facts_extracted", 0) for r in progress.values())
    total_stored = sum(r.get("facts_stored", 0) for r in progress.values())
    done = sum(1 for r in progress.values() if r.get("status") == "completed")
    failed = sum(1 for r in progress.values() if r.get("status") == "failed")
    stats = limiter.stats

    logger.info(
        f"Ingestion complete in {total_elapsed}s: {done} succeeded, "
        f"{failed} failed, {total_facts} facts extracted, "
        f"{total_stored} facts stored"
    )
    logger.info(
        f"Gradient2 final: limit={stats['current_limit']}, "
        f"long_rtt={stats['long_rtt']:.1f}s, "
        f"samples={stats['sample_count']}, drops={stats['drops_total']}"
    )

    return progress


def _as_completed_iter(futures: Dict[Future, str]):
    """Yield futures as they complete. Thin wrapper for testability."""
    from concurrent.futures import as_completed

    yield from as_completed(futures)
