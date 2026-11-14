# CommerceLens MVP acceptance

## Data and live scenarios

Two builds from the publisher archive each selected 15,000 of 99,441 source orders. Both produced the same order ID digest, monthly allocations, linked record counts and monetary totals. The databases were 7.09 and 7.61 MB. The build found zero checked relationship or key violations. It retained 16,894 items, 15,704 payments, 14,982 reviews, 9,122 products and 1,913 sellers. It materialized 15,065 seller-order pairs. It found 150 sampled products without an English category translation and used the Portuguese category where present.

- Olist archive SHA-256 `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`
- Sorted sample order ID SHA-256 `93e5d327a4b40f9017d09c0e1648f0142fbc499fac7e2217816d2edde7dce175`

A separate validation read the publisher ZIP with Python's CSV reader, filtered each source table by the corresponding retained relationship keys, and compared complete row multisets with all eight retained DuckDB source tables. Every table matched, including the multiplicity of reviews and payments. A fresh build reproduced the same sample digest and integrity checks. The CI suite also builds a synthetic archive twice to exercise monthly selection, linked-row retention, checksums, monetary grain, and rejection of null or duplicate payment keys.

Streamlit's Natural language mode was exercised with the local model and actual Olist sample. The logistics and commerce reports returned calculated comparisons and execution traces. Independent queries against the source tables confirmed the numerical outcomes.

| Scenario | June 2018 | July 2018 | Change |
| --- | ---: | ---: | ---: |
| Eligible late deliveries | 15 / 917 (1.64%) | 30 / 936 (3.21%) | +1.57 pp |
| Merchandise value proxy | R$139,360.38 | R$141,625.90 | +R$2,265.52 |
| Recorded payment value proxy | R$162,715.53 | R$166,395.04 | +R$3,679.51 |

The showcase separates calculated results, provisional business assumptions and conclusions the available data cannot confirm. For example, the warehouse inventory question displayed an unconfirmed conclusion. The JSON report includes query inputs, SQL, citations and the trace.

The initial merchandise demo excluded the end of each calendar month and showed a change of −R$1,759.03. The graph now supplies the whole-month convention and repairs a proposed last-day exclusive bound for an explicitly named whole month. Regression tests cover inclusion of the final day and preservation of explicit exclusive dates. Both Streamlit paths were rerun after the fix.

The live model also ran seller-order contributions for those periods. At seller-order grain the rate changed from 1.60% to 3.14%, with 722 sellers in the union of the two cohorts. The first attempt exhausted the bounded execution memory. A materialized seller-order relation removed the repeated join and deduplication work. The structured FastAPI review investigation and independent source SQL returned 4.29 stars across 13,494 eligible on-time orders with reviews and 2.39 across 955 late orders with reviews. One natural-language review query also returned an ineligible null group. Review differences are observational.

## Real model evaluation

All variants used local Qwen2.5-Coder-3B-Instruct Q4_K_M and the same 45 Olist cases. The 80 DataBench queries used five complete official test tables, the same model and the official value comparator. The metered API cost was $0. Raw per-case records with SQL, traces and usage remain in `reports/runs/`. Aggregate results are linked below.

| Olist variant | Task success | SQL execution accuracy | Numerical correctness | Tool correctness | P50 / P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| SQL | 28/45 | 72.2% | 71.4% | 84.4% | 1.10 / 1.99 s |
| SQL + RAG | 41/45 | 88.9% | 88.6% | 100% | 1.04 / 1.30 s |
| SQL + RAG + investigation | 40/45 | 84.4% | 85.7% | 100% | 1.08 / 1.33 s |
| Full with verification | 40/45 | 84.4% | 85.7% | 100% | 1.06 / 1.36 s |

The three variants with retrieval returned a relevant citation for all five definition tasks. Mean precision among displayed citations was 36.7% against the nominated sources. RAG alone had the highest task success in this run. The investigation tool answered all four contribution tasks. Verification did not change the Olist success count and did not catch the four date or eligibility mistakes on late-rate SQL and one extra review group. The [Olist aggregate JSON](olist-summary.json) includes SQL completion, token counts and failure distributions.

DataBench adapted subset passed 29/80 tasks (36.25%). SQL completed on 50/80, and 16/40 numerical answers matched the official comparator. P50/P95 were 0.79/1.52 seconds. Seventeen final plans were rejected by the table policy, twelve reached DuckDB but failed binding, and one failed parsing. Twenty-one completed queries returned a mismatched answer. Per-table success varied from 2/16 on IBM HR to 11/16 on NBA. The [DataBench aggregate JSON](databench-summary.json) records metrics and usage.

The Olist suite informed development changes and its numbers measure regression performance. The adapted DataBench results measure only the selected official test questions. A clean DataBench build reproduced the manifest's file hashes, complete source row counts and selected IDs. No score threshold was set for the MVP.

## Acceptance matrix

| Requirement | Evidence |
| --- | --- |
| Layered repository | Framework-free domain, application contracts and graph, infrastructure adapters, interface composition in bootstrap. |
| Reproducible Olist foundation | Two independent builds and matching logical sample checks. |
| Two real end-to-end scenarios | Streamlit interaction through localhost Qwen and independent raw SQL reconciliation. |
| SQL, RAG and evidence | Read-only DuckDB policy and integration tests, retrieval citations and timed graph traces. |
| Benchmark harness | Machine-readable task JSONL and aggregate JSON for both tracks. |
| Real baselines and error analysis | Local four-variant Olist ablation and 80-question DataBench adapted subset. |
| Deterministic engineering | 25 tests passed on the development Windows host, including the archive-to-database build. Cross-platform CI evidence is available on the MVP PR. |
| Interactive showcase | Local Streamlit health returned OK. Natural-language interactions exercised with Streamlit AppTest. |
| Documentation | README, architecture, evaluation and reproduction instructions checked against the implementation. |
| Independent human gold audit | Pending. Implementation audit and correction history are recorded in the evaluation protocol. |
