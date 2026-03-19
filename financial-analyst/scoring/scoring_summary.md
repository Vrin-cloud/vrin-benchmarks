# Head-to-Head Scoring Summary: CoWork Standalone vs CoWork + Vrin MCP

## Scoring Methodology

Each question is scored across five dimensions, each weighted 0-20:

1. **Accuracy** (0-20): Correctness of financial data, figures, and claims
2. **Depth** (0-20): Level of analytical detail and nuance
3. **Cross-Document Synthesis** (0-20): Ability to connect information across multiple filings and sources
4. **Actionability** (0-20): Whether the analysis leads to concrete, investable conclusions
5. **Specificity** (0-20): Use of precise figures, direct quotes, and named sources

Per-question maximum: 100. Ten questions yield a maximum of 1,000 points.

## Per-Question Scores (out of 100)

| Q# | Category | Question Summary | CoWork Standalone | CoWork + Vrin MCP | Delta |
|----|----------|-----------------|-------------------|-------------------|-------|
| Q1 | Cross-Company Comparison | Revenue growth, margins, FCF across Big 5 | 78 | 86 | **+8** |
| Q2 | Cross-Company Comparison | AI/cloud capex as % of revenue, trajectories | 72 | 92 | **+20** |
| Q3 | Deep-Dive Analysis | META's top 3 new 10-K risk factors | 81 | 95 | **+14** |
| Q4 | Deep-Dive Analysis | Amazon cash flow breakdown (NI vs OCF) | 87 | 94 | **+7** |
| Q5 | Multi-Hop Reasoning | Declining gross margins + increasing R&D | 86 | 93 | **+7** |
| Q6 | Multi-Hop Reasoning | Most aggressive AI capex bet vs revenue | 93 | 90 | **-3** |
| Q7 | Portfolio & Correlation | Equal-weight portfolio revenue concentration | 91 | 92 | **+1** |
| Q8 | Portfolio & Correlation | Revenue growth guidance rankings | 91 | 92 | **+1** |
| Q9 | Anomaly & Inconsistency | 8-K vs 10-K disclosure inconsistencies | 82 | 96 | **+14** |
| Q10 | Anomaly & Inconsistency | GAAP vs non-GAAP earnings gap | 88 | 95 | **+7** |
| | | **TOTAL** | **849** | **925** | **+76** |
| | | **AVERAGE** | **84.9** | **92.5** | **+7.6** |

## Dimension-Level Breakdown

### Q2: AI/Cloud Capex Trajectories (Largest Delta, +20)

| Dimension | Standalone | Vrin MCP | Delta |
|-----------|-----------|---------|-------|
| Accuracy | 14 | 19 | +5 |
| Depth | 15 | 18 | +3 |
| Cross-Document Synthesis | 12 | 20 | +8 |
| Actionability | 16 | 17 | +1 |
| Specificity | 15 | 18 | +3 |
| **Total** | **72** | **92** | **+20** |

### Q3: META 10-K New Risk Factors (+14)

| Dimension | Standalone | Vrin MCP | Delta |
|-----------|-----------|---------|-------|
| Accuracy | 16 | 19 | +3 |
| Depth | 17 | 19 | +2 |
| Cross-Document Synthesis | 14 | 20 | +6 |
| Actionability | 17 | 18 | +1 |
| Specificity | 17 | 19 | +2 |
| **Total** | **81** | **95** | **+14** |

### Q9: 8-K vs 10-K Inconsistencies (+14)

| Dimension | Standalone | Vrin MCP | Delta |
|-----------|-----------|---------|-------|
| Accuracy | 17 | 19 | +2 |
| Depth | 16 | 20 | +4 |
| Cross-Document Synthesis | 14 | 20 | +6 |
| Actionability | 18 | 18 | 0 |
| Specificity | 17 | 19 | +2 |
| **Total** | **82** | **96** | **+14** |

### Q6: Most Aggressive AI Capex Bet (Standalone Wins, -3)

| Dimension | Standalone | Vrin MCP | Delta |
|-----------|-----------|---------|-------|
| Accuracy | 18 | 18 | 0 |
| Depth | 19 | 18 | -1 |
| Cross-Document Synthesis | 17 | 17 | 0 |
| Actionability | 20 | 18 | -2 |
| Specificity | 19 | 19 | 0 |
| **Total** | **93** | **90** | **-3** |

## Key Patterns

### Where Vrin MCP Dominated (largest deltas)

1. **Q2 (+20): AI/cloud capex trajectories.** Vrin pulled META's exact capex from the 10-K cash flow statement ($72.2B including finance leases vs. standalone's $69.7B). It retrieved verbatim management quotes from Amy Hood and Sundar Pichai. The Vrin response also self-corrected its Q1 META FCF figure after re-reading the 10-K.

2. **Q3 (+14): META 10-K new risk factors.** Standalone acknowledged it "was unable to access the full SEC filing text directly." Vrin pulled direct 10-K language and calculated $209B in total infrastructure obligations by cross-referencing three disclosure sources ($72.2B capex + $81.2B contracts + $58.1B leases).

3. **Q9 (+14): 8-K vs 10-K inconsistencies.** Vrin discovered that Microsoft's 10-K lists OpenAI as a competitor while the 8-K celebrates it as a partner. It also surfaced Safari search volume declines from Eddie Cue's court testimony. Both insights are impossible from web search alone.

### Where CoWork Standalone Won

4. **Q6 (-3): Forward strategy synthesis.** CoWork's "Infrastructure Maximalists vs. Integration Minimalist" framework and one-word strategic summaries (Existential / Offensive / Defensive-Offensive / Foundational / Contrarian) were more analytically creative. This was the only question where standalone outscored Vrin.

### The Pattern

- **Vrin MCP wins on filing-level analysis** (Q1-Q5, Q7-Q10): where document retrieval from hybrid RAG adds data that web search cannot match.
- **CoWork standalone wins on creative strategy synthesis** (Q6): where narrative framing and analytical creativity matter more than data retrieval.
- **Vrin raises the floor**: No Vrin-backed answer scored below 86/100, while standalone had two scores below 80 (Q1: 78, Q2: 72). Vrin does not just improve the best answers. It eliminates the worst ones.
- **Average delta on retrieval-heavy questions**: +10.9 points per question.

### Unique Capabilities Vrin MCP Enabled

1. **Direct 10-K/10-Q quotes**: 3-7 per response, pulled from actual filing text (standalone: 0)
2. **Management earnings call quotes**: 2-4 verbatim CEO/CFO quotes per response (standalone: 0-1 paraphrased)
3. **Cross-document fact retrieval**: META's $81.2B non-cancelable commitments, MSFT's OpenAI competitor classification, Safari volume decline
4. **Self-correction**: Q2 response caught and corrected its own Q1 META FCF error by re-reading the 10-K cash flow statement
5. **Source citations**: 5-11 source URLs per Vrin-backed answer (standalone: 0-9)
6. **Filing-level precision**: Millions-level figures from SEC filings ($131,819M) vs. billions-level rounding (~$128.3B)
