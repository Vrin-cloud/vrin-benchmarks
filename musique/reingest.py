"""Re-ingest failed MuSiQue paragraphs with storage verification.

Ingests paragraphs sequentially (or with low concurrency) and verifies
that both facts (Neptune) and chunks (OpenSearch) are actually stored
by querying VRIN after each ingestion.

Usage::

    python -m musique.reingest --api-key vrin_xxx
    python -m musique.reingest --api-key vrin_xxx --concurrency 3 --test 20
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from tqdm import tqdm
from vrin import VRINClient

from . import config
from .dataset import load_musique

logger = logging.getLogger(__name__)

RESULTS_DIR = config.RESULTS_DIR
REINGEST_IDS_FILE = RESULTS_DIR / "reingest_ids.json"
REINGEST_PROGRESS_FILE = RESULTS_DIR / "reingest_progress.json"


def _verify_storage(
    client: VRINClient,
    title: str,
    text_snippet: str,
) -> Dict[str, Any]:
    """Query VRIN to verify facts and chunks are retrievable for this paragraph."""
    # Use title as query — it's the Wikipedia article title, so it should
    # match entities extracted from the paragraph
    try:
        result = client.query(
            f"What do you know about {title}?",
            stream=False,
            response_mode="chat",
            include_summary=False,
        )
        metadata = result.get("metadata", {})
        return {
            "total_facts": result.get("total_facts", metadata.get("total_facts", 0)),
            "total_chunks": result.get("total_chunks", metadata.get("total_chunks", 0)),
            "verified": True,
        }
    except Exception as e:
        logger.warning(f"Verification query failed for '{title}': {e}")
        return {"total_facts": 0, "total_chunks": 0, "verified": False, "error": str(e)}


def _ingest_and_verify(
    client: VRINClient,
    para: Dict[str, str],
    verify: bool = True,
    retry_count: int = 2,
) -> Dict[str, Any]:
    """Ingest a single paragraph, wait for completion, and optionally verify storage."""
    start = time.time()
    pid = para["id"]

    for attempt in range(1, retry_count + 1):
        try:
            result = client.insert(
                para["text"],
                title=para["title"],
                tags=["musique-benchmark"],
                wait=True,
                max_wait=180.0,  # longer timeout
                poll_interval=3.0,  # slower polling to reduce pressure
            )

            job_id = result.get("job_id", "")
            facts_extracted = result.get("facts_extracted", 0)
            facts_stored = result.get("facts_stored", 0)

            # If no job_id, the async pipeline didn't kick in — flag it
            if not job_id:
                logger.warning(
                    f"[{pid[:8]}] No job_id returned (attempt {attempt}) — "
                    f"extracted={facts_extracted}, stored={facts_stored}"
                )
                if attempt < retry_count:
                    time.sleep(5)  # back off before retry
                    continue

            # Wait a bit for eventual consistency before verification
            if verify:
                time.sleep(2)
                verification = _verify_storage(client, para["title"], para["text"][:200])
            else:
                verification = {"verified": False}

            elapsed = round(time.time() - start, 1)

            record = {
                "id": pid,
                "title": para["title"],
                "status": "completed",
                "attempt": attempt,
                "job_id": job_id,
                "facts_extracted": facts_extracted,
                "facts_stored": facts_stored,
                "has_job_id": bool(job_id),
                "verification": verification,
                "elapsed_s": elapsed,
            }

            # Log result
            v_facts = verification.get("total_facts", "?")
            v_chunks = verification.get("total_chunks", "?")
            status_icon = "ok" if (facts_stored > 0 or job_id) else "WARN"
            logger.info(
                f"[{pid[:8]}] {status_icon} | extracted={facts_extracted} stored={facts_stored} "
                f"job_id={'yes' if job_id else 'NO'} | verify: facts={v_facts} chunks={v_chunks} "
                f"| {elapsed}s"
            )
            return record

        except Exception as e:
            logger.warning(f"[{pid[:8]}] Attempt {attempt} failed: {e}")
            if attempt < retry_count:
                time.sleep(5)
            else:
                return {
                    "id": pid,
                    "title": para["title"],
                    "status": "failed",
                    "attempt": attempt,
                    "error": str(e),
                    "elapsed_s": round(time.time() - start, 1),
                }

    # Should not reach here
    return {"id": pid, "status": "failed", "error": "exhausted retries"}


def _save_progress(progress: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(progress, f, indent=2)
    tmp.rename(path)


def run_reingest(
    client: VRINClient,
    concurrency: int = 3,
    verify: bool = True,
    test_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Re-ingest failed paragraphs with verification.

    Args:
        client: VRIN API client.
        concurrency: Max parallel ingestions (default 3, keep low).
        verify: If True, query VRIN after each insert to confirm storage.
        test_limit: If set, only process this many paragraphs (for testing).
    """
    # Load failed paragraph IDs
    if not REINGEST_IDS_FILE.exists():
        logger.error(f"No reingest IDs file at {REINGEST_IDS_FILE}")
        return {}

    with open(REINGEST_IDS_FILE) as f:
        reingest_ids = set(json.load(f))
    logger.info(f"Paragraphs to re-ingest: {len(reingest_ids)}")

    # Load original paragraphs from dataset
    paragraphs, _ = load_musique()
    para_map = {p["id"]: p for p in paragraphs}

    # Filter to only the ones we need to re-ingest
    to_ingest = [para_map[pid] for pid in reingest_ids if pid in para_map]
    logger.info(f"Found {len(to_ingest)} paragraphs in dataset (of {len(reingest_ids)} IDs)")

    if test_limit:
        to_ingest = to_ingest[:test_limit]
        logger.info(f"Test mode: limiting to {test_limit} paragraphs")

    # Load existing reingest progress (for resumability)
    progress: Dict[str, Any] = {}
    if REINGEST_PROGRESS_FILE.exists():
        with open(REINGEST_PROGRESS_FILE) as f:
            progress = json.load(f)

    already_done = {pid for pid, r in progress.items() if r.get("status") == "completed" and r.get("has_job_id")}
    remaining = [p for p in to_ingest if p["id"] not in already_done]
    logger.info(f"Already done: {len(already_done)}, remaining: {len(remaining)}")

    if not remaining:
        logger.info("All paragraphs already re-ingested")
        return progress

    # Stats tracking
    stats = {"success": 0, "no_job_id": 0, "failed": 0, "verified_with_chunks": 0}
    save_counter = 0

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(_ingest_and_verify, client, para, verify): para["id"]
            for para in remaining
        }

        for future in tqdm(as_completed(futures), total=len(futures), desc="Re-ingesting"):
            record = future.result()
            pid = record["id"]
            progress[pid] = record
            save_counter += 1

            # Track stats
            if record.get("status") == "completed":
                if record.get("has_job_id"):
                    stats["success"] += 1
                else:
                    stats["no_job_id"] += 1
                v = record.get("verification", {})
                if v.get("total_chunks", 0) > 0:
                    stats["verified_with_chunks"] += 1
            else:
                stats["failed"] += 1

            # Checkpoint every 10
            if save_counter % 10 == 0:
                _save_progress(progress, REINGEST_PROGRESS_FILE)
                logger.info(
                    f"--- Checkpoint {save_counter}/{len(remaining)} --- "
                    f"success={stats['success']} no_job_id={stats['no_job_id']} "
                    f"failed={stats['failed']} verified_chunks={stats['verified_with_chunks']}"
                )

    _save_progress(progress, REINGEST_PROGRESS_FILE)

    logger.info(
        f"\nRe-ingestion complete: "
        f"success={stats['success']} no_job_id={stats['no_job_id']} "
        f"failed={stats['failed']} verified_chunks={stats['verified_with_chunks']}"
    )
    return progress


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Re-ingest failed MuSiQue paragraphs")
    parser.add_argument("--api-key", default=config.VRIN_API_KEY, help="VRIN API key")
    parser.add_argument("--concurrency", type=int, default=3, help="Max parallel ingestions")
    parser.add_argument("--test", type=int, default=None, help="Limit to N paragraphs for testing")
    parser.add_argument("--no-verify", action="store_true", help="Skip verification queries")
    args = parser.parse_args()

    if not args.api_key:
        parser.error("--api-key is required (or set VRIN_API_KEY env var)")

    client = VRINClient(api_key=args.api_key)
    run_reingest(
        client,
        concurrency=args.concurrency,
        verify=not args.no_verify,
        test_limit=args.test,
    )


if __name__ == "__main__":
    main()
