#!/usr/bin/env python3
"""
MultiHop-RAG Benchmark - Null Queries Only

Runs only the 44 null_query questions from the same stratified sample (seed=42)
to measure v29 bail-out improvement. Combines with existing results for other types.
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from vrin import VRINClient
from benchmark_utils import (
    calculate_margin_of_error,
    stratified_sample,
    evaluate_multihop_answer,
    format_duration
)

LOG_FILE = Path(__file__).parent / "multihop_rag" / "logs" / f"null_only_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
RESULTS_FILE = Path(__file__).parent / "multihop_rag" / "results" / f"null_only_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def log(message: str) -> None:
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(log_msg + '\n')


def run_benchmark() -> None:
    data_file = Path(__file__).parent / "multihop_rag" / "data" / "queries_train.json"
    log(f"Loading dataset from: {data_file}")

    with open(data_file, 'r') as f:
        full_dataset = json.load(f)

    # Same stratified sample as all other runs (seed=42)
    sample, distribution = stratified_sample(
        full_dataset, 384, stratify_key='question_type', seed=42
    )

    # Filter to null queries only
    null_queries = [q for q in sample if q.get('question_type') == 'null_query']

    log("=" * 80)
    log("MultiHop-RAG Benchmark — NULL QUERIES ONLY (v29 bail-out test)")
    log(f"Null queries: {len(null_queries)} (from 384 stratified sample, seed=42)")
    log(f"Response mode: thinking")
    log("=" * 80)

    api_key = os.getenv('TEST_ACC_API_KEY')
    if not api_key:
        raise ValueError("TEST_ACC_API_KEY environment variable must be set.")
    client = VRINClient(api_key=api_key)
    log("VRIN Client initialized")

    results = []
    correct_answers = 0
    bail_out_count = 0
    match_types = defaultdict(int)
    start_time = time.time()

    for idx, item in enumerate(null_queries, 1):
        question_start = time.time()

        log(f"\n{'='*60}")
        log(f"Null Query {idx}/{len(null_queries)}")
        log(f"Query: {item['query'][:100]}...")
        log(f"Expected: {item['answer']}")

        try:
            query_result = client.query(item['query'], response_mode='thinking')
            vrin_answer = query_result.get('summary', query_result.get('response', ''))
            log(f"QUERY: Got response ({len(vrin_answer)} chars)")

            insufficient = (
                query_result.get('insufficient_coverage')
                or query_result.get('metadata', {}).get('insufficient_coverage', False)
            )
            if insufficient:
                log(f"BAIL-OUT triggered")
                bail_out_count += 1

            correct, match_type = evaluate_multihop_answer(
                item['answer'], vrin_answer, question=item['query']
            )
            match_types[match_type] += 1

            elapsed = time.time() - question_start
            if correct:
                log(f"CORRECT ({match_type}) — {format_duration(elapsed)}")
                correct_answers += 1
            else:
                log(f"INCORRECT ({match_type}) — {format_duration(elapsed)}")
                log(f"   VRIN: {vrin_answer[:200]}")

            results.append({
                'query': item['query'],
                'expected': item['answer'],
                'vrin_response': vrin_answer,
                'correct': correct,
                'match_type': match_type,
                'insufficient_coverage': bool(insufficient),
                'elapsed': elapsed
            })

        except Exception as e:
            log(f"QUERY FAILED: {str(e)}")
            results.append({
                'query': item['query'],
                'expected': item['answer'],
                'vrin_response': '',
                'correct': False,
                'match_type': 'query_failed',
                'insufficient_coverage': False,
                'elapsed': time.time() - question_start
            })

    total_elapsed = time.time() - start_time
    accuracy = (correct_answers / len(null_queries) * 100) if null_queries else 0

    log(f"\n{'='*80}")
    log("FINAL RESULTS — NULL QUERIES")
    log(f"{'='*80}")
    log(f"Accuracy: {accuracy:.1f}% ({correct_answers}/{len(null_queries)})")
    log(f"Bail-outs triggered: {bail_out_count}/{len(null_queries)}")
    log(f"Previous null accuracy: 63.6% (28/44)")
    log(f"Improvement: {accuracy - 63.6:+.1f}pp")
    log(f"Match types: {dict(match_types)}")
    log(f"Total time: {format_duration(total_elapsed)}")
    log(f"Avg time: {format_duration(total_elapsed / len(null_queries))}/query")

    # Combined accuracy with original results for other types
    # Original: Inference 122/123, Comparison 122/129, Temporal 79/88, Null 28/44
    original_other = 122 + 122 + 79  # 323 correct out of 340
    new_total_correct = original_other + correct_answers
    new_overall = new_total_correct / 384 * 100
    log(f"\nCOMBINED (original other types + new null):")
    log(f"   Overall: {new_overall:.1f}% ({new_total_correct}/384)")
    log(f"   Previous overall: 91.4% (351/384)")
    log(f"   Change: {new_overall - 91.4:+.1f}pp")

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    final_results = {
        'benchmark': 'MultiHop-RAG — Null Queries Only (v29 bail-out test)',
        'timestamp': datetime.now().isoformat(),
        'null_accuracy': round(accuracy, 2),
        'null_correct': correct_answers,
        'null_total': len(null_queries),
        'bail_out_count': bail_out_count,
        'previous_null_accuracy': 63.6,
        'combined_overall': round(new_overall, 2),
        'previous_overall': 91.4,
        'match_types': dict(match_types),
        'total_time_seconds': round(total_elapsed, 1),
        'avg_time_per_query': round(total_elapsed / len(null_queries), 1),
        'detailed_results': results
    }

    with open(RESULTS_FILE, 'w') as f:
        json.dump(final_results, f, indent=2)

    log(f"\nResults: {RESULTS_FILE}")
    log(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    try:
        run_benchmark()
    except KeyboardInterrupt:
        log("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\nFATAL: {str(e)}")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)
