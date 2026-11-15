# CommerceLens roadmap

## Phase I — Foundation & Feasibility

**Engineering complete.** Phase I covers the initial repository through the capability diagnosis in [PR #12](https://github.com/re-tourist/commerce-analytics-agent/pull/12). Its objective was to establish a reproducible path from a natural-language question to a bounded query and inspectable evidence.

| Milestone | Phase I scope |
| --- | --- |
| M1 Data Foundation | Pinned Olist source, reproducible 15,000-order sample, and metric definitions. |
| M2 Agent MVP | Read-only DuckDB, business-definition retrieval, analysis tools, and evidence traces. |
| M3 Evaluation | Paired benchmarks and error audits delivered. Independent human review of all 45 Olist references remains open in [#7](https://github.com/re-tourist/commerce-analytics-agent/issues/7). |
| M4 Showcase | Streamlit walkthrough, exported evidence, clean installation, and Windows and Ubuntu CI. |

The default user path uses the full Olist agent with retrieval, analysis tools, and bounded verification. The documented local model is Qwen2.5-Coder-3B-Instruct Q4_K_M. Olist task accuracy was 40/45 for that path and 30/45 for 7B. An experimental month-boundary and delivery-eligibility prompt raised those regression results to 45/45 and 39/45 respectively. This candidate still needs independent validation before use in the default path.

On the 48-question DataBench regression cohort, DDL grounding and targeted retry raised accuracy from 3/48 to 15/48 for 3B and from 8/48 to 23/48 for 7B. Doubling the 3B generation cap changed no final SQL on 72 paired questions. The Typed Analysis Plan improved simple boolean answers while reducing total correct answers on the 24-question development set from 9 to 5 for 3B and from 8 to 7 for 7B. It remains a research prototype. Previously exposed DataBench questions serve as development and regression evidence. [Experiment details and costs](../reports/capability-diagnosis.md)

Phase I establishes engineering feasibility. The remaining reliability gaps include correct date windows, metric eligibility and grain, schema binding, and valid-looking SQL with wrong answers. Formal Olist reference acceptance remains pending independent human review.

Engineering baseline from the five integration PRs: [7c319d658767b24513afa646a1c32157e6cf9f5a](https://github.com/re-tourist/commerce-analytics-agent/commit/7c319d658767b24513afa646a1c32157e6cf9f5a).

## Phase II — Reliability & Generalization

Track this phase in [the Phase II tracking issue #13](https://github.com/re-tourist/commerce-analytics-agent/issues/13).
Dataset construction is delivered as a frozen candidate: [397 tasks, split policy and quality evidence](BENCHMARKS.md).
Independent Olist review and owner-controlled Test isolation remain open. The release is
`FROZEN_CANDIDATE_NOT_BLIND`; no new Test model experiments or algorithm changes are included.
Method selection and reliability implementation remain separate future work.

1. Collect new Olist questions with independently reviewed references. Freeze the cohort and grading before comparing candidates.
2. Validate Semantic Grounding for dates, units, eligibility and grain. Measure accuracy and paired regressions.
3. Evaluate Semantic Verification against independently defined invariants. Record false positives and missed semantic errors.
4. Check correctness across database schemas and use narrow compiler experiments where failure evidence supports them. Compare models on identical tasks.

Maintain phase progress and decisions here and in the linked Issues and PRs. Start new work from the verified Phase I baseline on `main`.
