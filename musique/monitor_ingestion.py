"""Monitor VRIN fact extraction Lambda logs during ingestion.

Tails CloudWatch logs for FACT_EXTRACTION_SUMMARY and errors, printing
real-time stats on throughput, failure rate, and storage health.

Usage::

    python -m musique.monitor_ingestion
    # Ctrl+C to stop
"""

import re
import sys
import time

import boto3

LOG_GROUP = "/aws/lambda/vrin-fact-extraction-handler"
REGION = "us-east-1"
POLL_INTERVAL = 10  # seconds between CloudWatch polls

# Counters
stats = {
    "summaries": 0,
    "total_chunks": 0,
    "total_facts_extracted": 0,
    "total_facts_stored": 0,
    "total_entities": 0,
    "errors": 0,
    "throttles": 0,
    "zero_fact_count": 0,
    "zero_chunk_count": 0,
}


def parse_summary(msg: str) -> dict | None:
    """Parse FACT_EXTRACTION_SUMMARY log line."""
    m = re.search(
        r"chunks=(\d+), entities_identified=(\d+), "
        r"facts_extracted=(\d+), unique_facts=(\d+)",
        msg,
    )
    if m:
        return {
            "chunks": int(m.group(1)),
            "entities": int(m.group(2)),
            "facts_extracted": int(m.group(3)),
            "unique_facts": int(m.group(4)),
        }
    return None


def is_real_error(msg: str) -> bool:
    """Filter out non-critical errors (usage tracking)."""
    if "Error logging API key usage" in msg:
        return False
    if "VALIDATION FAILED" in msg:
        return False  # fact validation is expected
    if "ERROR" in msg or "FAILED" in msg or "BLOCKED" in msg:
        return True
    return False


def is_throttle(msg: str) -> bool:
    return ("throttl" in msg.lower() or "TooManyRequests" in msg
            or "rate exceeded" in msg.lower()
            or " 429 " in msg or " 429," in msg)


def main() -> None:
    client = boto3.client("logs", region_name=REGION)

    # Start from now
    start_time = int(time.time() * 1000)
    next_token = None
    run_start = time.time()

    print(f"Monitoring {LOG_GROUP}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print("=" * 80)
    print(f"{'Time':>8}  {'Done':>5}  {'Chunks':>6}  {'Facts':>6}  "
          f"{'Stored':>6}  {'0-fact':>6}  {'Errors':>6}  {'Throttle':>8}  {'Rate':>8}")
    print("-" * 80)

    try:
        while True:
            kwargs = {
                "logGroupName": LOG_GROUP,
                "startTime": start_time,
                "interleaved": True,
                "limit": 200,
            }
            if next_token:
                kwargs["nextToken"] = next_token

            try:
                resp = client.filter_log_events(**kwargs)
            except Exception as e:
                print(f"  [CloudWatch error: {e}]", file=sys.stderr)
                time.sleep(POLL_INTERVAL)
                continue

            events = resp.get("events", [])
            new_next = resp.get("nextToken")

            for event in events:
                msg = event.get("message", "")
                ts = event.get("timestamp", 0)

                # Update start_time to avoid re-reading
                if ts > start_time:
                    start_time = ts + 1

                # Parse summaries
                if "FACT_EXTRACTION_SUMMARY" in msg:
                    parsed = parse_summary(msg)
                    if parsed:
                        stats["summaries"] += 1
                        stats["total_chunks"] += parsed["chunks"]
                        stats["total_facts_extracted"] += parsed["facts_extracted"]
                        stats["total_facts_stored"] += parsed["unique_facts"]
                        stats["total_entities"] += parsed["entities"]
                        if parsed["facts_extracted"] == 0:
                            stats["zero_fact_count"] += 1
                        if parsed["chunks"] == 0:
                            stats["zero_chunk_count"] += 1

                # Check errors
                if is_throttle(msg):
                    stats["throttles"] += 1
                    print(f"\n  *** THROTTLE DETECTED: {msg[:200]}")
                elif is_real_error(msg):
                    stats["errors"] += 1
                    print(f"\n  *** ERROR: {msg[:200]}")

            # Update next_token for pagination
            if new_next and new_next != next_token:
                next_token = new_next
            else:
                next_token = None

            # Print stats line
            elapsed = time.time() - run_start
            rate = stats["summaries"] / elapsed * 60 if elapsed > 0 else 0
            elapsed_str = f"{int(elapsed//60)}m{int(elapsed%60):02d}s"

            print(
                f"\r{elapsed_str:>8}  "
                f"{stats['summaries']:>5}  "
                f"{stats['total_chunks']:>6}  "
                f"{stats['total_facts_extracted']:>6}  "
                f"{stats['total_facts_stored']:>6}  "
                f"{stats['zero_fact_count']:>6}  "
                f"{stats['errors']:>6}  "
                f"{stats['throttles']:>8}  "
                f"{rate:>6.1f}/m",
                end="",
                flush=True,
            )

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        elapsed = time.time() - run_start
        print(f"\n\n{'='*80}")
        print(f"MONITORING STOPPED after {elapsed/60:.1f} min")
        print(f"  Paragraphs processed: {stats['summaries']}")
        print(f"  Total chunks stored:  {stats['total_chunks']}")
        print(f"  Total facts extracted: {stats['total_facts_extracted']}")
        print(f"  Total facts stored:   {stats['total_facts_stored']}")
        print(f"  Zero-fact paragraphs: {stats['zero_fact_count']}")
        print(f"  Errors:               {stats['errors']}")
        print(f"  Throttles:            {stats['throttles']}")
        if stats['summaries'] > 0:
            print(f"  Avg facts/paragraph:  {stats['total_facts_extracted']/stats['summaries']:.1f}")
            print(f"  Avg chunks/paragraph: {stats['total_chunks']/stats['summaries']:.1f}")
        print(f"{'='*80}")


if __name__ == "__main__":
    main()
