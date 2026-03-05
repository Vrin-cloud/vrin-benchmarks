"""MuSiQue evaluation: Exact Match and Token F1.

Uses the standard SQuAD-style normalization (lowercase, strip articles,
punctuation, and extra whitespace) and computes EM/F1 against gold answers
plus any answer aliases.
"""

import math
import re
import string
from collections import Counter
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# SQuAD-style normalization
# ---------------------------------------------------------------------------


def normalize_answer(s: str) -> str:
    """Lowercase, strip articles / punctuation / extra whitespace."""

    def remove_articles(text: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def remove_punc(text: str) -> str:
        return "".join(ch for ch in text if ch not in string.punctuation)

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    return white_space_fix(remove_articles(remove_punc(s.lower())))


# ---------------------------------------------------------------------------
# Per-example metrics
# ---------------------------------------------------------------------------


def exact_match(prediction: str, gold: str) -> float:
    return float(normalize_answer(prediction) == normalize_answer(gold))


def token_f1(prediction: str, gold: str) -> float:
    pred_tokens = normalize_answer(prediction).split()
    gold_tokens = normalize_answer(gold).split()

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    common = Counter(pred_tokens) & Counter(gold_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0

    precision = num_same / len(pred_tokens)
    recall = num_same / len(gold_tokens)
    return (2 * precision * recall) / (precision + recall)


def score_single(
    prediction: str, gold: str, aliases: List[str] | None = None
) -> Tuple[float, float]:
    """Best EM and F1 across the gold answer and all aliases."""
    candidates = [gold] + (aliases or [])
    best_em = max(exact_match(prediction, c) for c in candidates)
    best_f1 = max(token_f1(prediction, c) for c in candidates)
    return best_em, best_f1


# ---------------------------------------------------------------------------
# Aggregate evaluation
# ---------------------------------------------------------------------------


def evaluate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate EM, F1, and per-complexity breakdowns.

    Args:
        results: list of per-question dicts from ``query.run_queries()``.

    Returns:
        Metrics dict with ``exact_match``, ``token_f1``, breakdowns, etc.
    """
    ems: List[float] = []
    f1s: List[float] = []
    insuff_count = 0
    latencies: List[int] = []
    facts_counts: List[int] = []
    chunks_counts: List[int] = []
    by_complexity: Dict[str, Dict[str, Any]] = {}

    for r in results:
        if r.get("status") != "completed":
            continue

        pred = r.get("extracted_answer", "")
        gold = r.get("gold_answer", "")
        aliases = r.get("gold_aliases", [])

        if r.get("insufficient_coverage"):
            insuff_count += 1
            em, f1 = 0.0, 0.0
        else:
            em, f1 = score_single(pred, gold, aliases)

        ems.append(em)
        f1s.append(f1)
        latencies.append(r.get("latency_ms", 0))
        facts_counts.append(r.get("vrin_facts_count", 0))
        chunks_counts.append(r.get("vrin_chunks_count", 0))

        # Per-complexity tracking
        complexity = r.get("auto_complexity") or "unknown"
        if complexity not in by_complexity:
            by_complexity[complexity] = {"ems": [], "f1s": [], "count": 0}
        by_complexity[complexity]["ems"].append(em)
        by_complexity[complexity]["f1s"].append(f1)
        by_complexity[complexity]["count"] += 1

    n = len(ems)
    if n == 0:
        return {"error": "No completed results to evaluate"}

    metrics: Dict[str, Any] = {
        "n": n,
        "exact_match": round(sum(ems) / n, 4),
        "token_f1": round(sum(f1s) / n, 4),
        "insufficient_coverage_rate": round(insuff_count / n * 100, 1),
        "avg_latency_ms": round(sum(latencies) / n),
        "avg_facts_retrieved": round(sum(facts_counts) / n, 1),
        "avg_chunks_retrieved": round(sum(chunks_counts) / n, 1),
        "by_complexity": {},
    }

    for complexity, data in sorted(by_complexity.items()):
        c = data["count"]
        metrics["by_complexity"][complexity] = {
            "n": c,
            "exact_match": round(sum(data["ems"]) / c, 4) if c else 0,
            "token_f1": round(sum(data["f1s"]) / c, 4) if c else 0,
        }

    return metrics


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------


def print_report(metrics: Dict[str, Any]) -> None:
    """Print a formatted benchmark report to stdout."""
    n = metrics["n"]
    # Margin of error (simplified — no finite population correction)
    moe = 1.96 * math.sqrt(0.5 * 0.5 / n) * 100

    print(f"\nMuSiQue Benchmark Results (N={n}, +/-{moe:.1f}%)")
    print("-" * 45)
    print(f"Exact Match:          {metrics['exact_match']:.3f}")
    print(f"Token F1:             {metrics['token_f1']:.3f}")
    print(f"Insuff. Coverage:     {metrics['insufficient_coverage_rate']}%")
    print(f"Avg Latency:          {metrics['avg_latency_ms']}ms")
    print(f"Avg Facts Retrieved:  {metrics['avg_facts_retrieved']}")
    print(f"Avg Chunks Retrieved: {metrics['avg_chunks_retrieved']}")

    if metrics.get("by_complexity"):
        print(f"\nBy Auto-Complexity:")
        for complexity, data in metrics["by_complexity"].items():
            print(
                f"  {complexity:12s}: "
                f"EM={data['exact_match']:.3f}  "
                f"F1={data['token_f1']:.3f}  "
                f"(N={data['n']})"
            )
