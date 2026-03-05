#!/usr/bin/env python3
"""
MultiHop-RAG Benchmark - Query Only (No Ingestion)

Runs the same 384 stratified queries against an account that already has
the benchmark documents ingested. Skips the insert step entirely.

Usage:
    export TEST_ACC_API_KEY="vrin_xxxx"
    python run_multihop_query_only.py
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

# Configuration
SAMPLE_SIZE = 384
LOG_FILE = Path(__file__).parent / "multihop_rag" / "logs" / f"query_only_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
RESULTS_FILE = Path(__file__).parent / "multihop_rag" / "results" / f"query_only_{SAMPLE_SIZE}_sample_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def log(message):
    """Write to log file and print"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(log_msg + '\n')


def run_benchmark():
    # Load dataset
    data_file = Path(__file__).parent / "multihop_rag" / "data" / "queries_train.json"
    log(f"Loading dataset from: {data_file}")

    with open(data_file, 'r') as f:
        full_dataset = json.load(f)

    population_size = len(full_dataset)
    log(f"Full dataset size: {population_size} questions")

    margin_of_error = calculate_margin_of_error(SAMPLE_SIZE, population_size)

    log("=" * 80)
    log("MultiHop-RAG Benchmark (QUERY ONLY - No Ingestion)")
    log(f"Sample Size: {SAMPLE_SIZE} questions")
    log(f"Population Size: {population_size} questions")
    log(f"Margin of Error: ±{margin_of_error}% at 95% confidence")
    log(f"Sampling Method: Stratified by question_type")
    log(f"Log File: {LOG_FILE}")
    log("=" * 80)

    # Stratified sampling — same seed=42 as original benchmark
    sample, question_type_distribution = stratified_sample(
        full_dataset,
        SAMPLE_SIZE,
        stratify_key='question_type',
        seed=42
    )
    log(f"Stratified sample of {len(sample)} questions by question_type")
    log(f"Distribution: {json.dumps(question_type_distribution)}")

    # Initialize client
    api_key = os.getenv('TEST_ACC_API_KEY')
    if not api_key:
        raise ValueError("TEST_ACC_API_KEY environment variable must be set.")
    client = VRINClient(api_key=api_key)
    log(f"VRIN Client initialized (query-only mode)")

    # Tracking
    results = []
    correct_answers = 0
    match_types = defaultdict(int)
    accuracy_by_type = defaultdict(lambda: {'correct': 0, 'total': 0})
    start_time = time.time()

    for idx, item in enumerate(sample, 1):
        question_start = time.time()
        question_type = item.get('question_type', 'unknown')

        log(f"\n{'='*60}")
        log(f"Question {idx}/{len(sample)}")
        log(f"Query: {item['query'][:80]}...")
        log(f"Expected: {item['answer']}")
        log(f"Type: {question_type}")

        # Query only — no insertion
        try:
            query_result = client.query(item['query'], response_mode='research')
            vrin_answer = query_result.get('summary', query_result.get('response', ''))
            log(f"QUERY: Got response ({len(vrin_answer)} chars)")

            # Check if bail-out triggered (field is in metadata from SSE)
            insufficient = (
                query_result.get('insufficient_coverage')
                or query_result.get('metadata', {}).get('insufficient_coverage', False)
            )
            if insufficient:
                log(f"BAIL-OUT: insufficient_coverage=True")

            correct, match_type = evaluate_multihop_answer(
                item['answer'],
                vrin_answer,
                question=item['query']
            )
            match_types[match_type] += 1

            if correct:
                log(f"CORRECT ({match_type})")
                correct_answers += 1
                accuracy_by_type[question_type]['correct'] += 1
            else:
                log(f"INCORRECT")
                log(f"   VRIN (first 150 chars): {vrin_answer[:150]}")

            accuracy_by_type[question_type]['total'] += 1
            question_elapsed = time.time() - question_start
            log(f"Time: {format_duration(question_elapsed)}")

            results.append({
                'query': item['query'],
                'expected': item['answer'],
                'vrin_response': vrin_answer,
                'question_type': question_type,
                'correct': correct,
                'match_type': match_type,
                'insufficient_coverage': bool(insufficient),
                'elapsed': question_elapsed
            })

        except Exception as e:
            log(f"QUERY FAILED: {str(e)}")
            accuracy_by_type[question_type]['total'] += 1
            results.append({
                'query': item['query'],
                'expected': item['answer'],
                'vrin_response': '',
                'question_type': question_type,
                'correct': False,
                'match_type': 'query_failed',
                'insufficient_coverage': False,
                'elapsed': time.time() - question_start
            })

        # Progress every 10 questions
        if idx % 10 == 0:
            elapsed = time.time() - start_time
            avg_time = elapsed / idx
            remaining = (len(sample) - idx) * avg_time
            current_accuracy = correct_answers / idx * 100
            log(f"\nPROGRESS:")
            log(f"   Completed: {idx}/{len(sample)} ({idx/len(sample)*100:.1f}%)")
            log(f"   Correct: {correct_answers}/{idx} ({current_accuracy:.1f}%)")
            log(f"   Avg time: {format_duration(avg_time)}/question")
            log(f"   ETA: {format_duration(remaining)}")

    # Final summary
    total_elapsed = time.time() - start_time
    accuracy = (correct_answers / len(sample) * 100) if len(sample) > 0 else 0

    accuracy_by_type_pct = {}
    for q_type, stats in accuracy_by_type.items():
        if stats['total'] > 0:
            accuracy_by_type_pct[q_type] = {
                'correct': stats['correct'],
                'total': stats['total'],
                'accuracy': round(stats['correct'] / stats['total'] * 100, 1)
            }

    bail_out_count = sum(1 for r in results if r.get('insufficient_coverage'))

    log(f"\n{'='*80}")
    log("FINAL RESULTS")
    log(f"{'='*80}")
    log(f"Accuracy: {accuracy:.1f}% ({correct_answers}/{len(sample)})")
    log(f"Margin of Error: ±{margin_of_error}% at 95% confidence")
    log(f"Confidence Interval: [{accuracy - margin_of_error:.1f}%, {accuracy + margin_of_error:.1f}%]")
    log(f"Bail-outs (insufficient_coverage): {bail_out_count}")
    log(f"Total time: {format_duration(total_elapsed)}")
    log(f"\nMatch Types: {dict(match_types)}")
    log(f"\nAccuracy by Question Type:")
    for q_type, stats in sorted(accuracy_by_type_pct.items()):
        log(f"   {q_type}: {stats['accuracy']:.1f}% ({stats['correct']}/{stats['total']})")

    # Save results
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    final_results = {
        'benchmark': 'MultiHop-RAG (Query Only)',
        'dataset_source': 'yixuantt/MultiHopRAG',
        'timestamp': datetime.now().isoformat(),
        'note': 'Query-only run against pre-ingested data. No insertion step.',

        'sample_size': len(sample),
        'population_size': population_size,
        'sampling_method': 'stratified_by_question_type',
        'random_seed': 42,

        'confidence_level': '95%',
        'margin_of_error': f"±{margin_of_error}%",
        'confidence_interval': {
            'lower': round(accuracy - margin_of_error, 1),
            'upper': round(accuracy + margin_of_error, 1)
        },

        'accuracy': round(accuracy, 2),
        'correct_answers': correct_answers,
        'bail_out_count': bail_out_count,

        'match_types': dict(match_types),
        'question_type_distribution': question_type_distribution,
        'accuracy_by_question_type': accuracy_by_type_pct,

        'total_time_seconds': round(total_elapsed, 1),
        'avg_time_per_question': round(total_elapsed / len(sample), 1),

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
