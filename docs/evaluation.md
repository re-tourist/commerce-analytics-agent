# Evaluation protocol

## Olist business benchmark

The Olist suite contains 45 fixed cases and independent analysis references in `benchmarks/olist_cases.py`. References query the retained source tables and do not reuse the production analytical views. Four unavailable-field or causal cases expect abstention. Five definition cases expect a relevant business citation. The remaining 36 cases cover aggregate counts, joins, payments, category slices, late rates, ranked absolute contributions, review association and empty cohorts.

The graph sees only the question, analytical schema and configured metric information. Evaluation separately compares rows to reference SQL with an explicit order contract and a mixed absolute/relative numerical tolerance of 1e-6. Positional cells, row counts and truncation are checked. Investigation outputs are projected to the metric and shape required by the case. Data questions are scored on the result. SQL execution accuracy uses the SQL-routed subset and requires a correct result. The SQL completion rate separately measures execution. Numerical correctness uses cases with numerical reference output. Tool correctness checks the expected route family. Definition tasks report a hit in the retrieved citations and precision among shown citations using nominated references.

The ablation holds model weights, decoding settings and task IDs fixed across SQL, SQL + RAG, SQL + RAG + investigation, and full with verification. P50/P95 use nearest rank and include planning, query and graph work on the same local machine. The benchmark records reported usage and metered API cost. Errors are classified as model errors, tool errors, routing, retrieval or answer mismatches. Results are single local runs. Differences of a few tasks should be interpreted with the case mix and small sample in mind.

## DataBench adapted subset

This is an adapted test subset of SemEval 2025 Task 8 full-table QA. It uses five tables from the organizers' test declaration at revision `e75d53add267d2f9cfa32efd65ad77f0807adfad`. Each table is loaded in full. The selection takes 16 rows per table by rank of SHA-256 over seed 741 and the table-qualified zero-based QA row position. The file digests, row counts and frozen IDs are in the [subset manifest](databench-subset.json). The benchmark uses no train or development questions. [Official DataBench dataset and split declarations](https://huggingface.co/datasets/cardiffnlp/databench/tree/e75d53add267d2f9cfa32efd65ad77f0807adfad), [task paper](https://aclanthology.org/2025.semeval-1.324/)

The harness uses the official `databench-eval==4.0.1` comparison for boolean, number, category and list outputs. SQL result projection enforces one column, returns a scalar or list as required, and passes it to the official comparison. The agent sees one table with original rows and column names and receives only the question text. DataBench uses the full verifier with commerce-specific retrieval and investigation disabled. The reported score applies only to the adapted subset. [Official evaluator](https://github.com/jorses/databench_eval)

## Audit record

Reference SQL, test coverage and sample calculations received an implementation audit against source tables. The first live demo exposed month windows that ended before the last calendar day. Independent raw-table queries found a sign reversal in the merchandise change. The calendar repair and exact-date regression tests were added and the model runs repeated. See the [acceptance report](../reports/acceptance.md) for initial and final observations and the [Olist reference review](../benchmarks/REVIEW.md) for the pending human audit.
