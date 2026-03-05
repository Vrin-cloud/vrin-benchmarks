"""CLI orchestrator for the MuSiQue benchmark.

Usage::

    # Full pipeline (ingest -> query -> evaluate)
    python -m musique.run --api-key vrin_xxx

    # Individual steps
    python -m musique.run ingest   --api-key vrin_xxx
    python -m musique.run query    --api-key vrin_xxx
    python -m musique.run evaluate
    python -m musique.run report

    # Options
    python -m musique.run --sample-size 10 --api-key vrin_xxx   # smoke test
    python -m musique.run --query-depth thinking --api-key vrin_xxx
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from vrin import VRINClient

from . import config
from .dataset import load_musique
from .evaluate import evaluate, print_report
from .ingest import ingest_paragraphs
from .query import run_queries

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


def cmd_ingest(args: argparse.Namespace) -> None:
    client = VRINClient(api_key=args.api_key)
    paragraphs, questions = load_musique(args.sample_size, args.seed)
    logger.info(
        f"Loaded {len(paragraphs)} unique paragraphs "
        f"from {len(questions)} questions"
    )
    ingest_paragraphs(
        client, paragraphs, args.results_dir, args.ingest_concurrency
    )


def cmd_query(args: argparse.Namespace) -> None:
    client = VRINClient(api_key=args.api_key)
    _, questions = load_musique(args.sample_size, args.seed)
    logger.info(f"Loaded {len(questions)} questions")
    run_queries(
        client, questions, args.results_dir, args.query_depth, args.concurrency
    )


def cmd_evaluate(args: argparse.Namespace) -> None:
    results_file = args.results_dir / "query_results.json"
    if not results_file.exists():
        logger.error(f"No results at {results_file}. Run 'query' first.")
        sys.exit(1)

    with open(results_file) as f:
        results = json.load(f)

    metrics = evaluate(results)
    print_report(metrics)

    report_file = args.results_dir / "report.json"
    report = {
        "benchmark": "MuSiQue",
        "dataset": "bdsaglam/musique (answerable, validation)",
        "timestamp": datetime.now().isoformat(),
        **metrics,
    }
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Report saved to {report_file}")


def cmd_run_all(args: argparse.Namespace) -> None:
    """Full pipeline: ingest -> query -> evaluate."""
    start = time.time()

    client = VRINClient(api_key=args.api_key)

    # Load dataset
    logger.info("Loading MuSiQue dataset...")
    paragraphs, questions = load_musique(args.sample_size, args.seed)
    logger.info(
        f"  {len(paragraphs)} unique paragraphs, {len(questions)} questions"
    )

    # Ingest
    logger.info("Starting ingestion...")
    ingest_paragraphs(
        client, paragraphs, args.results_dir, args.ingest_concurrency
    )

    # Query
    logger.info("Starting queries...")
    results = run_queries(
        client, questions, args.results_dir, args.query_depth, args.concurrency
    )

    # Evaluate
    metrics = evaluate(results)
    print_report(metrics)

    total_time = round(time.time() - start, 1)
    report_file = args.results_dir / "report.json"
    report = {
        "benchmark": "MuSiQue",
        "dataset": "bdsaglam/musique (answerable, validation)",
        "timestamp": datetime.now().isoformat(),
        "total_time_seconds": total_time,
        **metrics,
    }
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Done in {total_time}s. Report: {report_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MuSiQue multi-hop QA benchmark for VRIN"
    )
    parser.add_argument(
        "--api-key",
        default=config.VRIN_API_KEY,
        help="VRIN API key (or set VRIN_API_KEY env var)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=config.SAMPLE_SIZE,
        help="Number of questions to sample (default: 400)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=config.RANDOM_SEED,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--query-depth",
        default=config.QUERY_DEPTH,
        choices=["basic", "thinking", "research"],
        help="Override auto-routing depth (default: auto)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=config.QUERY_CONCURRENCY,
        help="Query parallelism (default: 5)",
    )
    parser.add_argument(
        "--ingest-concurrency",
        type=int,
        default=config.INGEST_CONCURRENCY,
        help="Ingestion parallelism (default: 10)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=config.RESULTS_DIR,
        help="Directory for output files",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("ingest", help="Ingest paragraphs only")
    sub.add_parser("query", help="Run queries only")
    sub.add_parser("evaluate", help="Score existing results")
    sub.add_parser("report", help="Print report from existing results")

    args = parser.parse_args()

    # evaluate/report don't need an API key
    needs_key = args.command not in ("evaluate", "report")
    if needs_key and not args.api_key:
        parser.error(
            "--api-key is required (or set VRIN_API_KEY env var)"
        )

    args.results_dir.mkdir(parents=True, exist_ok=True)

    handlers = {
        "ingest": cmd_ingest,
        "query": cmd_query,
        "evaluate": cmd_evaluate,
        "report": cmd_evaluate,  # report is an alias for evaluate
        None: cmd_run_all,
    }

    try:
        handlers[args.command](args)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
