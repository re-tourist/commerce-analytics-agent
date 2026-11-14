# DataBench schema-grounding experiment

## Question and method

The MVP's 80-task DataBench adapted subset had 17 final relation-policy rejections and 12 binding errors. This experiment tests whether explicit schema grounding and targeted retry guidance improve completion and answer accuracy on unfamiliar tables.

The baseline is the MVP Full Agent with its existing two-attempt budget. The candidate uses the same model, policies, options and budget. It shows exact, quoted table and column identifiers in SQL DDL notation and adds a targeted instruction when validation rejects a relation or DuckDB reports a binding error. These two retry hints use the allowlisted schema and fixed text. The planner does not receive raw database exceptions, rejected relation or column names, labels or reference answers. SQL still follows the same read-only policy, allowlists and resource caps.

The candidate was frozen at `69833ff` after testing synthetic cases and the official dev subset. The dev run used two complete development tables and 12 deterministic cases per table. The test comparison uses the unchanged 80-question MVP selection across five complete official test tables. The test set was previously used for the MVP measurement. This is a new paired run on that fixed subset. [Official DataBench revision](https://huggingface.co/datasets/cardiffnlp/databench/tree/e75d53add267d2f9cfa32efd65ad77f0807adfad)

Both variants used the same local Qwen2.5-Coder-3B-Instruct Q4_K_M weights, llama.cpp b12383, temperature zero and seed 741. The same official comparator graded all cases. SQL completion counts tasks with a result from the SQL tool, including empty results. Task success applies the answer comparator and rejects truncated results. Latency is wall time per request and includes model calls and query execution. The baseline ran first in each split. Sequential runs can be affected by system load and warm-up.

## Development results

| Metric | Full baseline | Schema-grounded full |
| --- | ---: | ---: |
| Task success | 5/24 | 9/24 |
| SQL completed | 12/24 | 24/24 |
| Numerical correctness | 3/9 | 5/9 |
| Model calls | 36 | 24 |
| Input / output tokens | 6,626 / 981 | 6,262 / 638 |
| P50 / P95 | 1.42 / 2.39 s | 0.66 / 0.80 s |
| Metered API cost | $0 | $0 |

All twelve relation-policy failures were in the Bakery table. The candidate recovered three correct answers and nine mismatched answers from those failures. It also corrected one previously mismatched answer in the Pokémon table and retained the five existing passes.

## Paired test results

| Metric | Full baseline | Schema-grounded full |
| --- | ---: | ---: |
| Task success | 29/80 (36.25%) | 43/80 (53.75%) |
| SQL completed | 50/80 (62.5%) | 76/80 (95.0%) |
| Numerical correctness | 16/40 | 26/40 |
| Relation-policy rejections | 17 | 0 |
| Binding errors | 12 | 2 |
| Parse failures | 1 | 2 |
| Completed queries with mismatched answers | 21 | 33 |
| Model calls | 114 | 87 |
| Input / output tokens | 30,121 / 3,048 | 31,163 / 2,363 |
| P50 / P95 | 0.87 / 1.66 s | 1.45 / 1.98 s |
| Metered API cost | $0 | $0 |

The paired baseline reproduced each archived MVP task's success, execution and failure category. Of 30 original tool failures, 14 became correct, 12 executed with mismatched answers and four remained tool failures. One original mismatch became correct. One prior success on NBA regressed to an answer mismatch. The largest gains were on IBM HR (+6), Admissions (+5) and Coffee (+4).

The experiment improved answer accuracy by 17.5 percentage points on the fixed subset and improved execution on the tables that frequently failed relation or column binding. The additional executed queries still contained logic errors, and median latency rose by 0.57 seconds despite fewer model calls. Both changes are measured for this configuration and test selection. The experiment changes schema notation and retry hints together, so it cannot identify their individual effects. The candidate remains opt-in, and these results do not change the MVP defaults or its formal acceptance status.

## Reproduce

Use the pinned local inference runtime described in the [MVP reproduction guide](../docs/reproduction.md).

```sh
python -m benchmarks.databench --split dev --fetch
python -m benchmarks.databench --split test --fetch
python -m benchmarks.run databench --split dev --compare-schema-grounding --output reports/runs/schema-grounding-dev
python -m benchmarks.run databench --split test --compare-schema-grounding --output reports/runs/schema-grounding-test
python -m benchmarks.compare_grounding reports/runs/schema-grounding-dev/records.jsonl --output reports/runs/schema-grounding-dev/paired.json
python -m benchmarks.compare_grounding reports/runs/schema-grounding-test/records.jsonl --output reports/runs/schema-grounding-test/paired.json
```

The [development manifest](../docs/databench-dev-subset.json) and [test manifest](../docs/databench-subset.json) pin file checksums, selected IDs and table row counts. Raw model outputs stay in ignored local storage. The [machine-readable results](schema-grounding-results.json) contain both split summaries, transitions, per-table counts and run provenance.
