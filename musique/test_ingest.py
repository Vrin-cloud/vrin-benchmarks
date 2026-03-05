"""Test ingestion of 20 paragraphs with verification.

Ingests 20 paragraphs with 3 workers, then checks Neptune (facts) and
OpenSearch (chunks) to confirm everything is properly stored.

Usage::

    VRIN_API_KEY=vrin_ff2160037c6a1afb python -m musique.test_ingest
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from vrin import VRINClient

from . import config
from .dataset import load_musique

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

TEST_COUNT = 20
CONCURRENCY = 3
VERIFY_DELAY = 5  # seconds to wait before verification queries


def ingest_one(client: VRINClient, para: Dict[str, str]) -> Dict[str, Any]:
    """Insert a single paragraph and return result."""
    start = time.time()
    pid = para["id"][:8]
    try:
        result = client.insert(
            para["text"],
            title=para["title"],
            tags=["musique-benchmark"],
            wait=True,
            max_wait=180.0,
            poll_interval=3.0,
        )
        elapsed = round(time.time() - start, 1)
        facts_extracted = result.get("facts_extracted", 0)
        facts_stored = result.get("facts_stored", 0)
        job_id = result.get("job_id", "")
        logger.info(
            f"[{pid}] DONE | extracted={facts_extracted} stored={facts_stored} "
            f"job_id={'yes' if job_id else 'NO'} | {elapsed}s"
        )
        return {
            "id": para["id"],
            "title": para["title"],
            "status": "completed",
            "facts_extracted": facts_extracted,
            "facts_stored": facts_stored,
            "job_id": job_id,
            "elapsed_s": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        logger.error(f"[{pid}] FAILED | {e} | {elapsed}s")
        return {
            "id": para["id"],
            "title": para["title"],
            "status": "failed",
            "error": str(e),
            "elapsed_s": elapsed,
        }


def verify_storage(client: VRINClient, paragraphs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Query VRIN for each paragraph's title to verify facts+chunks are retrievable."""
    results = []
    for para in paragraphs:
        title = para["title"]
        try:
            result = client.query(
                f"What do you know about {title}?",
                stream=False,
                response_mode="chat",
                include_summary=False,
            )
            metadata = result.get("metadata", {})
            facts = result.get("total_facts", metadata.get("total_facts", 0))
            chunks = result.get("total_chunks", metadata.get("total_chunks", 0))
            results.append({
                "title": title,
                "paragraph_id": para["id"][:8],
                "facts": facts,
                "chunks": chunks,
                "ok": facts > 0 or chunks > 0,
            })
            logger.info(f"  VERIFY [{para['id'][:8]}] {title}: facts={facts}, chunks={chunks}")
        except Exception as e:
            results.append({
                "title": title,
                "paragraph_id": para["id"][:8],
                "facts": 0,
                "chunks": 0,
                "ok": False,
                "error": str(e),
            })
            logger.error(f"  VERIFY [{para['id'][:8]}] {title}: ERROR {e}")
    return results


def main() -> None:
    api_key = config.VRIN_API_KEY
    if not api_key:
        raise ValueError("Set VRIN_API_KEY env var (vrin_ff2160037c6a1afb)")

    client = VRINClient(api_key=api_key)
    logger.info(f"API key: {api_key[:10]}...{api_key[-4:]}")

    # Load dataset, take first 20 paragraphs
    paragraphs, questions = load_musique()
    test_paras = paragraphs[:TEST_COUNT]
    logger.info(f"Test ingesting {len(test_paras)} paragraphs with {CONCURRENCY} workers")

    # Print what we're ingesting
    for i, p in enumerate(test_paras):
        logger.info(f"  [{i+1:2d}] {p['id'][:8]} - {p['title']} ({len(p['text'])} chars)")

    # Ingest
    start = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(ingest_one, client, p): p["id"] for p in test_paras}
        for future in as_completed(futures):
            results.append(future.result())

    elapsed = round(time.time() - start, 1)
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_facts = sum(r.get("facts_extracted", 0) for r in results)
    total_stored = sum(r.get("facts_stored", 0) for r in results)
    with_job_id = sum(1 for r in results if r.get("job_id"))

    logger.info(f"\n{'='*60}")
    logger.info(f"INGESTION COMPLETE ({elapsed}s)")
    logger.info(f"  Completed: {completed}/{len(test_paras)}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Facts extracted: {total_facts}")
    logger.info(f"  Facts stored: {total_stored}")
    logger.info(f"  With job_id: {with_job_id}")
    logger.info(f"{'='*60}\n")

    # Wait for eventual consistency
    logger.info(f"Waiting {VERIFY_DELAY}s for storage consistency...")
    time.sleep(VERIFY_DELAY)

    # Verify
    logger.info("Verifying storage (querying each paragraph's title)...")
    verifications = verify_storage(client, test_paras)

    verified_ok = sum(1 for v in verifications if v["ok"])
    with_facts = sum(1 for v in verifications if v["facts"] > 0)
    with_chunks = sum(1 for v in verifications if v["chunks"] > 0)

    logger.info(f"\n{'='*60}")
    logger.info(f"VERIFICATION RESULTS")
    logger.info(f"  Retrievable (facts or chunks > 0): {verified_ok}/{len(verifications)}")
    logger.info(f"  With facts: {with_facts}")
    logger.info(f"  With chunks: {with_chunks}")

    # Flag any that have 0 chunks (the problem from last run)
    no_chunks = [v for v in verifications if v["chunks"] == 0]
    if no_chunks:
        logger.warning(f"  WARNING: {len(no_chunks)} paragraphs have 0 chunks!")
        for v in no_chunks:
            logger.warning(f"    [{v['paragraph_id']}] {v['title']}: facts={v['facts']}, chunks=0")

    no_facts = [v for v in verifications if v["facts"] == 0]
    if no_facts:
        logger.warning(f"  WARNING: {len(no_facts)} paragraphs have 0 facts!")
        for v in no_facts:
            logger.warning(f"    [{v['paragraph_id']}] {v['title']}: facts=0, chunks={v['chunks']}")

    logger.info(f"{'='*60}")

    # Save test results
    output = {
        "ingestion": results,
        "verification": verifications,
        "summary": {
            "ingested": completed,
            "failed": failed,
            "verified_ok": verified_ok,
            "with_facts": with_facts,
            "with_chunks": with_chunks,
            "no_chunks": len(no_chunks),
            "no_facts": len(no_facts),
        },
    }
    out_path = config.RESULTS_DIR / "test_ingest_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
