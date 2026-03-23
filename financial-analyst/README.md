# Financial Analyst Benchmark: CoWork Standalone vs CoWork + VRIN MCP

A head-to-head evaluation of AI-assisted financial analysis comparing **Claude CoWork (standalone)** against **Claude CoWork + VRIN MCP** across 10 cross-document financial reasoning questions about Big Tech (AAPL, MSFT, GOOGL, AMZN, META).

## Summary

| System | Total Score (out of 1,000) | Average per Question |
|--------|---------------------------|---------------------|
| CoWork Standalone | 824 | 82.4 |
| **CoWork + VRIN MCP** | **922** | **92.2** |
| **Delta** | **+98** | **+9.8** |

VRIN MCP improved performance on **9 out of 10 questions**, with the largest gains on filing-level deep dives (+20 on Q3, +19 on Q2, +13 on Q9).

## What Was Tested

**Two systems, same model, same questions, answered sequentially.**

- **CoWork Standalone**: Claude CoWork with access to locally downloaded SEC filing documents (10-K, 10-Q, 8-K, earnings transcripts for all 5 companies) + web search
- **CoWork + VRIN MCP**: The same Claude CoWork, but with local files removed and [VRIN's MCP server](https://vrin.cloud) connected instead — providing hybrid RAG access (knowledge graph + vector search) over the same SEC filings, plus web search

### Companies Covered
Apple (AAPL), Microsoft (MSFT), Alphabet/Google (GOOGL), Amazon (AMZN), Meta Platforms (META)

### Documents Ingested
Per company: 10-K annual filing, 10-Q quarterly filing, 8-K earnings press release, earnings call transcript

## Questions

10 questions across 5 categories designed to test cross-document financial reasoning:

| Category | Questions |
|----------|-----------|
| **Cross-Company Comparison** | Q1: Revenue/margins/FCF comparison (+9), Q2: AI capex trajectories (+19) |
| **Deep-Dive Analysis** | Q3: META's new 10-K risk factors (+20), Q4: Amazon cash flow breakdown (+9) |
| **Multi-Hop Reasoning** | Q5: Declining margins + rising R&D (+9), Q6: Most aggressive AI capex bet (-2) |
| **Portfolio & Correlation** | Q7: Portfolio revenue concentration (+5), Q8: Revenue growth guidance rankings (+6) |
| **Anomaly & Inconsistency** | Q9: 8-K vs 10-K inconsistencies (+13), Q10: GAAP vs non-GAAP earnings gap (+10) |

Full question text: [`questions.md`](questions.md)

## Scoring Methodology

Each question scored across 5 dimensions (0-20 each, 100 max per question):

1. **Accuracy** — Correctness of financial data, figures, and claims
2. **Depth** — Level of analytical detail and nuance
3. **Cross-Document Synthesis** — Ability to connect information across multiple filings
4. **Actionability** — Whether the analysis leads to concrete, investable conclusions
5. **Specificity** — Use of precise figures, direct quotes, and named sources

Full scoring breakdown: [`scoring/scoring_summary.md`](scoring/scoring_summary.md)

## Key Findings

### Three Findings That Matter

- **Multi-Source Reasoning**: When asked how much Meta has committed to AI infrastructure, VRIN pulled three separate disclosure sources from the annual report: $72.2B in capital expenditures, $81.2B in non-cancelable purchase commitments, and $58.1B in lease obligations — $209B in total committed spending. The standalone system found only the headline capex figure, understating Meta's true exposure by roughly two-thirds.

- **Self-Correction**: VRIN caught and corrected its own earlier mistake. In Q1, it reported that Meta's free cash flow grew 19.5%. Two questions later, while analyzing capital spending trajectories, it re-read the actual filing, realized the figure was wrong, and corrected it to a 16.3% decline ($43.6B). No human prompted this.

- **Cross-Filing Pattern Detection**: VRIN found that Microsoft's quarterly OpenAI investment swings wildly: a $3.1B loss one quarter, a $7.6B gain the next. These swings reverse the direction of Microsoft's earnings gap each quarter — a pattern only visible when reading across multiple filings.

### Where CoWork Standalone Won

- **Q6 (-2): Forward strategy synthesis** — CoWork's narrative framing ("Infrastructure Maximalists vs Integration Minimalists") and one-word strategic summaries per company were more analytically creative. This was the only question where standalone outscored VRIN.

### The Pattern

- **VRIN MCP wins on filing-level analysis** (Q1-Q5, Q7-Q10) — where document retrieval from knowledge graphs surfaces data that web search cannot match
- **CoWork standalone wins on creative strategy synthesis** (Q6) — where narrative framing and analytical creativity matter more than data retrieval
- **VRIN raises the floor**: Lowest VRIN-backed score was 89/100 vs standalone's 74/100. It doesn't just improve the best answers — it eliminates the worst ones.

## Full Report

[Download the benchmark report (PDF)](report.pdf) — designed for sharing with financial professionals and influencers.

## Repository Structure

```
financial-analyst/
├── README.md                              # This file
├── report.pdf                             # Full benchmark report (shareable)
├── questions.md                           # The 10 benchmark questions
├── responses/
│   ├── cowork-standalone/q01-q10.md       # Baseline responses
│   └── cowork-vrin-mcp/Q1-Q9.md, q10.md  # VRIN-enhanced responses
└── scoring/
    └── scoring_summary.md                 # Detailed per-question scoring
```

## About VRIN

[VRIN](https://vrin.cloud) is a hybrid RAG platform combining knowledge graphs with vector search for enterprise document intelligence. It exposes an MCP (Model Context Protocol) server that any compatible AI assistant can connect to — enabling structured, sourced, temporally-aware retrieval over ingested documents.

Learn more at [vrin.cloud](https://vrin.cloud).
