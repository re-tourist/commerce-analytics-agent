# CommerceLens semantic correctness and external holdout

The [33-case audit](semantic-error-audit.md) identifies boolean semantics and extra projection columns in 23 of the prior 33 executable mismatches. All 33 final queries reproduced their recorded rows and official judgments on replay. Replay executes the archived SQL. Only the development, ablation and holdout runs below measure model behavior.

## Protocol and isolation

| Cohort | Official partition | Purpose |
| --- | --- | --- |
| Development | Dev, 2 complete tables, 24 questions | Compare the semantic prompt with the existing combined configuration. |
| Previously exposed | Test, the original 5 complete tables and 80 questions | Audit the prior errors and separate DDL schema formatting from targeted retry. |
| Independent holdout | Test, 4 other complete tables, 48 questions | Evaluate the frozen candidate once on tables unused in earlier CommerceLens tuning. |

The [holdout manifest](../docs/databench-holdout.json) pins COL, Lift, Mortality and Books from the official DataBench revision. These are four compact tables selected using the official test declaration and Parquet sizes. Selection used file and row metadata, without inspecting questions or gold answers. Each table contributes the 12 lowest SHA-256 ranks of seed 741 and the table-qualified QA row ID. The table set is disjoint from both prior manifests. The candidate and manifest were committed as `16ee3965bba92f83b75c48a108445e6b251fea6a` before building the holdout or running it. This is a project-level holdout adapted from a public benchmark. Exposure during model pretraining is unknown. [Official DataBench revision](https://huggingface.co/datasets/cardiffnlp/databench/tree/e75d53add267d2f9cfa32efd65ad77f0807adfad)

The model sees the question and allowed table schema, plus the configured instructions. Gold labels and answer types stay in the evaluator. All arms use the same Qwen2.5-Coder-3B-Instruct Q4_K_M weights, llama.cpp b12383, temperature 0, seed 741, at most 384 generated tokens per call and at most two model attempts. The adapter retains a 4-second SQL timeout, 128 MB DuckDB memory budget, 200-row and 100,000-byte output limits, function and relation allowlists, read-only mode and disabled external access. The scorer is the unchanged DataBench adapter using `databench-eval==4.0.1`.

## Development and component ablation

On the 24 development questions, adding generic semantic guidance changed accuracy from 9/24 to 10/24, while both arms completed SQL on all 24 questions. The instruction asks the planner to identify measure, eligible rows, grain and answer type, evaluate a predicate for yes/no and project only the requested answer. It uses no benchmark-specific rules, new query tools or additional model calls.

| Previously exposed 80-question subset | DDL | Targeted retry | Correct | SQL completed |
| --- | --- | --- | ---: | ---: |
| Full baseline | Off | Off | 29/80 | 50/80 |
| Full with DDL only | On | Off | 42/80 | 74/80 |
| Full with targeted retry only | Off | On | 30/80 | 52/80 |
| PR #9 combined | On | On | 43/80 | 76/80 |

The baseline and combined arms are archived real runs from PR #9. The two isolated arms are new real runs under the same model and scoring settings. The revised flags preserve the other arm's setting. The retry comparison measures diagnostic wording, since all arms already retry within the same two-attempt budget. Under either retry setting, adding the DDL prompting package adds 13 correct answers and 24 completed queries. Under either DDL setting, adding targeted feedback adds one correct answer and two completed queries. These are net counts, with paired changes in the machine-readable results. Timing across archived and new sessions was collected for provenance and should be interpreted descriptively.

## Independent holdout results

| Metric | Full baseline | DDL + targeted retry | DDL + targeted retry + semantic instruction |
| --- | ---: | ---: | ---: |
| Task success | 3/48 (6.25%) | 15/48 (31.25%) | 12/48 (25.0%) |
| SQL completed | 15/48 | 33/48 | 30/48 |
| Numerical correctness | 1/21 | 8/21 | 7/21 |
| Completed with wrong answer | 12 | 18 | 18 |
| Relation-policy failures | 9 | 0 | 0 |
| Parsing or validation failures | 19 | 13 | 14 |
| Binding errors | 5 | 2 | 4 |
| Model calls | 82 | 65 | 67 |
| Input / output tokens | 15,638 / 2,399 | 17,072 / 1,917 | 24,803 / 1,969 |
| P50 / P95 | 1.34 / 2.76 s | 0.74 / 1.56 s | 0.79 / 1.61 s |
| Metered API cost | USD 0 | USD 0 | USD 0 |

DDL plus retry recovered 12 answers and retained all three baseline passes. The semantic instruction recovered zero additional answers and regressed three. Mortality case `075_Mortality:008` stopped using the grouped rate sum in ranking and failed binding. Books case `080_Books:013` introduced a stock filter, and `080_Books:037` collapsed rows by category. The candidate also consumed 7,731 additional input tokens. The positive dev delta did not carry over to this holdout. The semantic instruction stays experimental.

For the combined arm, all 13 parsing or validation failures displayed unquoted multiword identifiers or backtick quoting in the final proposed SQL. An identifier-handling intervention may target this failure mode, but it was not evaluated here. The new holdout supports transfer of the combined schema treatment to these four tables. It does not establish that the isolated DDL and retry effects transfer individually or that the method generalizes across DataBench. Latency figures reflect sequential runs on one local runtime.

## Reproduction

Start the pinned local model from the [reproduction guide](../docs/reproduction.md). Existing PR #9 records may be used for its two arms. To reproduce from a clean checkout, compile the three data cohorts and run the commands below.

```sh
python -m benchmarks.databench --split dev --fetch
python -m benchmarks.databench --split test --fetch
python -m benchmarks.databench --split holdout --fetch
python -m benchmarks.run databench --split dev --variant full_schema_grounded --variant full_semantic --output reports/runs/semantic-dev
python -m benchmarks.run databench --split test --compare-schema-grounding --output reports/runs/schema-grounding-test
python -m benchmarks.run databench --split test --variant full_ddl_only --variant full_retry_only --output reports/runs/semantic-ablation
python -m benchmarks.run databench --split holdout --variant full --variant full_schema_grounded --variant full_semantic --output reports/runs/semantic-holdout
python -m benchmarks.semantic_results --freeze 16ee3965bba92f83b75c48a108445e6b251fea6a --output reports/semantic-results.json
python -m pytest -q
```

Use the last command for deterministic engineering checks. Synthetic planner and database fixtures cover the independent prompt toggles, the existing policy and disjoint manifests. These tests do not contribute to model scores. Local JSONL stores per-task execution evidence. The [machine-readable results](semantic-results.json) contain aggregate, per-table and paired counts without queries, questions or gold values.

## Delivery order

The remote `main` is the empty root commit `117ffb5`. There is no README on the default branch yet. PR #6 targets `main`. PR #9 targets PR #6's branch. This experiment targets PR #9's branch. Each child contains its parent's exact head in its ancestry. Both existing PRs remain open.

After explicit approval, merge PR #6 first so the README and pinned MVP appear on the default branch. Preserve the parent branch until PR #9 has been retargeted to `main` and its diff and CI rechecked. Then review PR #9, followed by this experiment after retargeting and rechecking again. A merge commit preserves the stack ancestry. If squash merge is required, transplant only the child commits onto the new base and verify the diff before updating the child PR. The research options are available through the benchmark CLI. Issue #7 separately tracks `PENDING_HUMAN_REVIEW`, which remains a gate for formal Olist benchmark acceptance.
