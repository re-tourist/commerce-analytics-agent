# CommerceLens MVP acceptance

## Data and live scenarios

Two builds from the publisher archive each selected 15,000 of 99,441 source orders. Both produced the same order ID digest, monthly allocations, linked record counts and monetary totals. The databases were 6.04 and 6.30 MB. The build found zero checked relationship or key violations. It retained 16,894 items, 15,704 payments, 14,982 reviews, 9,122 products and 1,913 sellers. It found 150 sampled products without an English category translation and used the Portuguese category where present.

- Olist archive SHA-256 `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`
- Sorted sample order ID SHA-256 `93e5d327a4b40f9017d09c0e1648f0142fbc499fac7e2217816d2edde7dce175`

Streamlit's Natural language mode was exercised with the local model and actual Olist sample. Both reports returned calculated comparisons and execution traces. Independent queries against the source tables confirmed the numerical outcomes.

| Scenario | June 2018 | July 2018 | Change |
| --- | ---: | ---: | ---: |
| Eligible late deliveries | 15 / 917 (1.64%) | 30 / 936 (3.21%) | +1.57 pp |
| Merchandise value proxy | R$139,360.38 | R$141,625.90 | +R$2,265.52 |

The initial merchandise demo excluded the end of each calendar month and showed a change of −R$1,759.03. The graph now supplies the whole-month convention and repairs a proposed last-day exclusive bound for an explicitly named whole month. Regression tests cover inclusion of the final day and preservation of explicit exclusive dates. Both Streamlit paths were rerun after the fix.

## Acceptance matrix

| Requirement | Evidence |
| --- | --- |
| Layered repository | Framework-free domain, application contracts and graph, infrastructure adapters, interface composition in bootstrap. |
| Reproducible Olist foundation | Two independent builds and matching logical sample checks. |
| Two real end-to-end scenarios | Streamlit interaction through localhost Qwen and independent raw SQL reconciliation. |
| SQL, RAG and evidence | Read-only DuckDB policy and integration tests, retrieval citations and timed graph traces. |
| Benchmark harness | Machine-readable task JSONL and aggregate JSON for both tracks. |
| Real baselines and error analysis | Local four-variant Olist ablation and 80-question DataBench adapted subset. |
| Deterministic engineering | 20 tests passed on the development Windows host. Cross-platform CI evidence will be linked once checks finish. |
| Interactive showcase | Local Streamlit health returned OK. Natural-language interactions exercised with Streamlit AppTest. |
| Documentation | README, architecture, evaluation and reproduction instructions checked against the implementation. |
| Independent human gold audit | Pending. Implementation audit and correction history are recorded in the evaluation protocol. |
