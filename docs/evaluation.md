# Evaluation protocol

## Phase II dataset release (2026-11-15)

The current dataset specification is [BENCHMARKS.md](BENCHMARKS.md), with machine-readable
[freeze manifest](../benchmarks/phase2/manifest.json) and [integrity audit](../benchmarks/phase2/audit.json).
There are 397 tasks: Development 237, Validation 60, and candidate Test 100.
Development supports error analysis, algorithm development and regression; it is not a model
parameter training set. Validation supports future method selection. Candidate Test is reserved
for one independently controlled final evaluation after the method and scoring protocol are locked.

All 197 historical tasks (45 Olist and 152 DataBench across 11 databases) have been exposed
to development or diagnosis and belong exclusively to Development / Regression. The legacy
DataBench CLI names `test`, `dev` and `holdout` remain compatibility aliases for their original
80/24/48-task regression cohorts. In particular, `holdout` is no longer independent. None of
these legacy names selects the new Phase II Test. Historical reports, task IDs, scoring rules
and published scores are preserved without rescoring.

Olist adds 40/20/40 tasks; DataBench adds 0/40/60 tasks with database-level isolation.
New Olist computation uses source-table reference SQL, independently of production views.
The same references are executed on the retained snapshot and a reconstruction from the pinned
publisher CSVs; that verifies source computation and provenance, not human interpretation of
the question. All 88 new SQL references are `AUTO_VERIFIED`. The 12 new explanation/abstention
tasks have explicit criteria and are `PENDING_HUMAN_REVIEW`. All 45 historical Olist questions
still await formal independent human acceptance; no new reference is human-approved.

The new Olist row grader requires the specified output shape/order, distinguishes NULL from
zero, uses exact boolean/string comparison, and applies each task's absolute numeric tolerance
(zero for exact-count-only results, otherwise 1e-6). Monetary source arithmetic uses DECIMAL;
materialized decimals carry a tagged decimal string and floating statistics are rounded to nine
decimal places. This avoids the historical relative tolerance admitting large absolute errors.
The Phase I protocol below continues unchanged for its historical cohort. Explanation tasks
require human assessment against every criterion and cannot pass from a fabricated automated score.

DataBench retains the exact official question, answer and semantic type, fixed revision
`e75d53add267d2f9cfa32efd65ad77f0807adfad`, full tables, and `databench-eval==4.0.1`.
New Validation uses four official development databases, and candidate Test uses six previously
unused official test databases. Official split membership and project split membership are recorded
separately. Reference round-trips and synthetic scorer tests verify format compatibility only;
they are neither model accuracy measurements nor an independent audit of official answer correctness.

Test isolation is **`FROZEN_CANDIDATE_NOT_BLIND`**. Test questions, SQL, rubrics and gold are
kept in ignored local `data/phase2/owner/`, never in the public repository. The public catalog
contains IDs, classifications, source summaries and commitments. The constructor has seen Test
information, the developer account can still read local files, and upstream DataBench gold is
publicly recoverable. File naming, Git ignore rules and a separate CLI do not establish blindness.
Development/Validation loaders have no Test resource path and reject Test before reading files.
The owner must move the complete frozen resource package to restricted storage, revoke developer
access, arrange independent reference review, freeze the candidate method, and run the separate
final process described in [BENCHMARKS.md](BENCHMARKS.md). No candidate model was run on new Test.

## Olist business benchmark

The Olist suite contains 45 fixed cases and independent analysis references in `benchmarks/olist_cases.py`. References query the retained source tables and do not reuse the production analytical views. Four unavailable-field or causal cases expect abstention. Five definition cases expect a relevant business citation. The remaining 36 cases cover aggregate counts, joins, payments, category slices, late rates, ranked absolute contributions, review association and empty cohorts.

The graph sees only the question, analytical schema and configured metric information. Evaluation separately compares rows to reference SQL with an explicit order contract and a mixed absolute/relative numerical tolerance of 1e-6. Positional cells, row counts and truncation are checked. Investigation outputs are projected to the metric and shape required by the case. Data questions are scored on the result. SQL execution accuracy uses the SQL-routed subset and requires a correct result. The SQL completion rate separately measures execution. Numerical correctness uses cases with numerical reference output. Tool correctness checks the expected route family. Definition tasks report a hit in the retrieved citations and precision among shown citations using nominated references.

The ablation holds model weights, decoding settings and task IDs fixed across SQL, SQL + RAG, SQL + RAG + investigation, and full with verification. P50/P95 use nearest rank and include planning, query and graph work on the same local machine. The benchmark records reported usage and metered API cost. Errors are classified as model errors, tool errors, routing, retrieval or answer mismatches. Results are single local runs. Differences of a few tasks should be interpreted with the case mix and small sample in mind.

The Olist suite was used during development to diagnose date, schema and eligibility errors. Its scores describe regression coverage on these fixed questions. The historical DataBench cohorts were also used during development and diagnosis; their original official split labels do not give them independent project Test status.

## DataBench adapted subset

The historical 80-question adapted subset of SemEval 2025 Task 8 full-table QA uses five tables from the organizers' test declaration at revision `e75d53add267d2f9cfa32efd65ad77f0807adfad`. Each table is loaded in full. The selection takes 16 rows per table by rank of SHA-256 over seed 741 and the table-qualified zero-based QA row position. The file digests, row counts and frozen IDs remain in the [subset manifest](databench-subset.json). The later [24-question cohort](databench-dev-subset.json) and [48-question cohort](databench-holdout.json) bring historical Development to 152 questions across 11 tables. The original JSON descriptions are retained as historical records and superseded by the current split registry. [Official DataBench dataset and split declarations](https://huggingface.co/datasets/cardiffnlp/databench/tree/e75d53add267d2f9cfa32efd65ad77f0807adfad), [task paper](https://aclanthology.org/2025.semeval-1.324/)

The harness uses the official `databench-eval==4.0.1` comparison for boolean, number, category and list outputs. SQL result projection enforces one column, returns a scalar or list as required, and passes it to the official comparison. The agent sees one table with original rows and column names and receives only the question text. DataBench uses the full verifier with commerce-specific retrieval and investigation disabled. The reported score applies only to the adapted subset. [Official evaluator](https://github.com/jorses/databench_eval)

## Audit record

Reference SQL, test coverage and sample calculations received an implementation audit against source tables. The first live demo exposed month windows that ended before the last calendar day. Independent raw-table queries found a sign reversal in the merchandise change. The calendar repair and exact-date regression tests were added and the model runs repeated.

Formal Olist benchmark acceptance is `PENDING_HUMAN_REVIEW`. CI establishes engineering reproducibility. The Olist numbers are measured regression results pending independent review of the reference set. See the [acceptance report](../reports/acceptance.md) and the [Olist reference review](../benchmarks/REVIEW.md).
