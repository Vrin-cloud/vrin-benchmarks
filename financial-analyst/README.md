# Financial Analyst Benchmark: CoWork Standalone vs CoWork + VRIN MCP

A head-to-head evaluation of AI-assisted financial analysis comparing **Claude CoWork (standalone)** against **Claude CoWork + VRIN MCP** across 10 cross-document financial reasoning questions about Big Tech (AAPL, MSFT, GOOGL, AMZN, META).

## Summary

| System | Total Score (out of 1,000) | Average per Question |
|--------|---------------------------|---------------------|
| CoWork Standalone | 849 | 84.9 |
| **CoWork + VRIN MCP** | **925** | **92.5** |
| **Delta** | **+76** | **+7.6** |

VRIN MCP improved performance on **9 out of 10 questions**, with the largest gains on filing-level deep dives (+20 on Q2, +14 on Q3 and Q9).

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
| **Cross-Company Comparison** | Q1: Revenue/margins/FCF comparison, Q2: AI capex as % of revenue |
| **Deep-Dive Analysis** | Q3: META's new 10-K risk factors, Q4: Amazon cash flow breakdown |
| **Multi-Hop Reasoning** | Q5: Declining margins + rising R&D, Q6: Most aggressive AI capex bet |
| **Portfolio & Correlation** | Q7: Portfolio revenue concentration, Q8: Revenue growth guidance rankings |
| **Anomaly & Inconsistency** | Q9: 8-K vs 10-K inconsistencies, Q10: GAAP vs non-GAAP earnings gap |

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

### Where VRIN MCP Dominated

- **Q9 (+14): 8-K vs 10-K inconsistency detection** — VRIN discovered that Microsoft's 10-K lists OpenAI as a *competitor* while the 8-K celebrates it as a strategic partner. Also surfaced that Apple executive Eddie Cue testified Safari search volumes declined for the first time in 22 years. These insights are impossible from web search alone.

- **Q2 (+20): Forward capex analysis** — VRIN provided 2026 guidance tables with dollar figures, direct management quotes from earnings call transcripts, and META's $81.2B in non-cancelable contractual commitments sourced from 10-K footnotes.

- **Q3 (+14): META risk factor deep-dive** — VRIN pulled direct 10-K quotes, calculated $209B in total META infrastructure obligations across 3 filing sources, and identified the useful-life accounting change as an impairment early warning.

### Where CoWork Standalone Held

- **Q6 (-3): Forward strategy synthesis** — CoWork's narrative framing ("Infrastructure Maximalists vs Integration Minimalist") and strategic one-word summaries per company were more analytically creative.

### The Pattern

- **VRIN MCP wins on backward-looking filing analysis** (Q2, Q3, Q4, Q5, Q9, Q10) — where document retrieval from knowledge graphs surfaces data that web search cannot match
- **CoWork standalone holds on forward-looking strategy synthesis** (Q6) — where narrative framing and analytical creativity matter more than data retrieval
- **VRIN raises the floor**: Lowest VRIN-backed score was 86/100 vs standalone's 72/100

## Repository Structure

```
financial-analyst/
├── README.md                              # This file
├── questions.md                           # The 10 benchmark questions
├── responses/
│   ├── cowork-standalone/q01-q10.md       # Baseline responses
│   └── cowork-vrin-mcp/q01-q10.md         # VRIN-enhanced responses
└── scoring/
    └── scoring_summary.md                 # Detailed per-question scoring
```

## About VRIN

[VRIN](https://vrin.cloud) is a hybrid RAG platform combining knowledge graphs with vector search for enterprise document intelligence. It exposes an MCP (Model Context Protocol) server that any compatible AI assistant can connect to — enabling structured, sourced, temporally-aware retrieval over ingested documents.

Learn more at [vrin.cloud](https://vrin.cloud).
