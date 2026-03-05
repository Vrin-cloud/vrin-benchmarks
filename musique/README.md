# MuSiQue Benchmark for VRIN

Multi-hop QA benchmark using [MuSiQue](https://arxiv.org/abs/2108.00573) (Multihop Questions via Single-hop Question Composition) to measure VRIN's multi-hop reasoning quality.

## What is MuSiQue?

MuSiQue is a challenging multi-hop QA dataset where each question requires reasoning across 2-4 Wikipedia paragraphs. Unlike simpler benchmarks, the questions are constructed to be unanswerable from any single paragraph — you *must* connect facts across documents.

We use the **answerable validation split** (2,417 questions), sampling 400 for a ±3.8% margin of error at 95% confidence.

**Reference points**: EcphoryRAG EM: 0.295, HippoRAG 2 F1: 0.486, Standard RAG F1: 0.457

## Quick Start

```bash
cd vrin-benchmarks

# Install dependencies
pip install -r requirements.txt

# Set keys
export VRIN_API_KEY=vrin_xxx
export OPENAI_API_KEY=sk-xxx  # for answer extraction via GPT-4o-mini

# Smoke test (10 questions)
python -m musique.run --api-key $VRIN_API_KEY --sample-size 10

# Full benchmark (400 questions)
python -m musique.run --api-key $VRIN_API_KEY
```

## Individual Steps

```bash
# Ingest paragraphs only
python -m musique.run ingest --api-key $VRIN_API_KEY

# Run queries only (after ingestion)
python -m musique.run query --api-key $VRIN_API_KEY

# Evaluate existing results (no API key needed)
python -m musique.run evaluate

# Override auto-routing with fixed depth
python -m musique.run --query-depth thinking --api-key $VRIN_API_KEY
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--api-key` | `$VRIN_API_KEY` | VRIN API key |
| `--sample-size` | 400 | Number of questions |
| `--seed` | 42 | Random seed |
| `--query-depth` | auto | Override: `basic`, `thinking`, `research` |
| `--concurrency` | 5 | Query parallelism |
| `--ingest-concurrency` | 10 | Ingestion parallelism |
| `--results-dir` | `musique/results/` | Output directory |

## Metrics

- **Exact Match (EM)**: Normalized prediction equals normalized gold answer
- **Token F1**: Token-level precision/recall between prediction and gold
- **Insufficient Coverage Rate**: % of questions where VRIN bailed out
- **By Auto-Complexity**: Breakdown by v32 auto-routing classification (SIMPLE/MODERATE/COMPLEX)

Normalization is SQuAD-style: lowercase, strip articles (`a`, `an`, `the`), punctuation, and extra whitespace. Scoring checks against gold answer + all aliases.

## Cost Estimate

- **Ingestion**: ~4,500 paragraphs × ~$0.0004 = ~$2
- **Queries**: 400 × ~$0.02 = ~$8
- **Answer extraction**: 400 × ~$0.001 (GPT-4o-mini) = ~$0.40
- **Total**: ~$10-12
- **Time**: ~2-3 hours

## Output

Results are saved to `musique/results/`:
- `ingest_progress.json` — per-paragraph ingestion status (resumable)
- `query_results.json` — per-question VRIN responses + extracted answers (resumable)
- `report.json` — aggregate EM, F1, and complexity breakdowns

Both ingestion and queries are resumable — interrupted runs pick up where they left off.
