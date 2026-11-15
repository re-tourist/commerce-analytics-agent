# CommerceLens Phase II datasets

Release: `phase2-candidate-v2`, frozen 2026-11-15. Status: **`FROZEN_CANDIDATE_NOT_BLIND`**.
This release constructs datasets only. It makes no model-performance claim and performs no
model selection, prompt tuning, Agent optimization or model inference experiment.

| Dataset | Development / Regression | Validation | Candidate Test | Total |
| --- | ---: | ---: | ---: | ---: |
| Olist | 45 historical + 40 new = 85 | 20 new | 40 new | 145 |
| DataBench | 152 historical | 40 new | 60 new | 252 |
| Total | 237 | 60 | 100 | 397 |

Development is for diagnosis and algorithm development, **not parameter training**.
Validation is for future method selection. Test is for the final independently controlled
assessment after methods and grading are locked. All 197 exposed historical tasks are preserved
only in Development, including the former DataBench `holdout`.

## Sources and database assignments

Olist uses [publisher version 2](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
CC BY-NC-SA 4.0, archive SHA-256 `967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784`.
The existing 15,000-order sample, seed 741, monthly proportional largest-remainder quotas and
linked records are unchanged. Sorted order IDs joined by LF (no terminal LF) have SHA-256
`93e5d327a4b40f9017d09c0e1648f0142fbc499fac7e2217816d2edde7dce175`.
Snapshot totals describe the retained sample, not all Olist sales or Brazilian retail.

| Olist assignment | IDs |
| --- | --- |
| Development | O001–O045 historical; O046–O085 new |
| Validation | O086–O105 |
| Candidate Test | O106–O145; content controlled locally |

DataBench uses [official files and declarations](https://huggingface.co/datasets/cardiffnlp/databench/tree/e75d53add267d2f9cfa32efd65ad77f0807adfad),
MIT, revision `e75d53add267d2f9cfa32efd65ad77f0807adfad`, with full `all.parquet` tables,
unaltered `qa.parquet` question/answer/type fields, and the
[official evaluator](https://github.com/jorses/databench_eval) pinned at `databench-eval==4.0.1`.
Project splits differ from official split names: official development databases may serve as
project Validation; exposed official test databases are project Development.

| Project split | Databases | Questions per database |
| --- | --- | --- |
| Development | 051_Pokemon, 060_Bakery | 12 each; original official dev |
| Development | 066_IBM_HR, 072_Admissions, 073_Med_Cost, 076_NBA, 079_Coffee | 16 each; original official test |
| Development | 071_COL, 074_Lift, 075_Mortality, 080_Books | 12 each; former project holdout |
| Validation | 052_Professional, 053_Patents, 054_Joe, 055_German | 10 each; unused official dev |
| Candidate Test | 067_TripAdvisor, 068_WorldBank_Awards, 069_Taxonomy, 070_OpenFoodFacts, 077_Gestational, 078_Fires | 10 each; unused official test |

The 11/4/6 database sets are disjoint. New databases were chosen from the untouched official
dev/test declarations, with four contiguous available dev tables and all six remaining unused
official test tables; this is a deliberate cohort, not a representative random sample of schemas.
Historical selections use their existing seed-741 IDs unchanged. New sampling uses the declared
per-table/type quotas in `benchmarks.build_phase2.PLAN`, then ascending raw SHA-256 bytes of
UTF-8 `20261115:{database_id}:{zero_based_row:03}`. Reject near duplicates against historical
and previously selected questions and continue within the same type; fail rather than pad if
a quota cannot be met. One official German question was excluded by that rule. Every chosen
ID, QA/table hash, byte count, table row count, schema hash and source split is frozen in
[sources.json](../benchmarks/phase2/sources.json). IDs identify immutable zero-based QA rows,
not a claim that the upstream dataset provides a native ID column.

## Coverage and quality status

New Olist questions are authored by business objective, not by changing dates or states in
old templates. Their questions and contracts state scope, grain, units, denominators, missing
data behavior, ordering, ties and time windows where relevant. Questions remain in English,
consistent with the historical suite. Static difficulty tags reflect required operations;
they have not been calibrated using model performance.

| New Olist family | Development | Validation | Candidate Test |
| --- | ---: | ---: | ---: |
| Basic aggregates and composition | 8 | 4 | 6 |
| Group / period comparisons | 8 | 3 | 7 |
| Rankings and contribution | 6 | 3 | 7 |
| Multiple conditions, joins and grain | 8 | 4 | 9 |
| NULL, duplication, empty / boundary cases | 6 | 3 | 6 |
| Unsupported data, interpretation and causal limits | 4 | 3 | 5 |

The 100 additions include 14 basic, 53 intermediate and 33 advanced tasks. All 88 computational
references query `source.*`, with read-only SQL validation excluding production views. Source
row multisets are verified against publisher CSVs; reference results agree on retained and
archive-reconstructed source tables under the declared absolute tolerances. Using the same
SQL on independently reconstructed data validates execution/provenance, **not an independently
authored calculation or human judgment about the question's business meaning**. Source money
uses DECIMAL, continuous durations use explicit days/hours, date-only lateness is separate from
timestamp duration, many-side joins aggregate first, and empty sums retain NULL.
Gold materialization uses the single-thread publisher-CSV reconstruction in pinned file order;
retained DB physical/parallel scan order cannot change frozen floating aggregate bytes.
The unpublished construction candidate v1 was superseded by v2 to fix floating-order stability;
questions, assignments and historical results were unchanged, and neither candidate was blind.

New computational tasks are `AUTO_VERIFIED`, never human-approved. The other 12 have at least
four explicit, conjunctive human criteria and remain `PENDING_HUMAN_REVIEW`; a numerical proxy
cannot silently substitute for an unavailable metric or causal effect. All 45 historical Olist
questions still require independent acceptance under [REVIEW.md](../benchmarks/REVIEW.md) and
[issue #7](https://github.com/re-tourist/commerce-analytics-agent/issues/7).
Reviewers must record their name, date, task IDs, frozen source/resource hashes, criterion-level
findings, proposed corrections and retest evidence. Reference acceptance and later human scoring
of a candidate's explanation are distinct activities. Any change to frozen content needs a new
release/hash, a disclosed reason and fresh independent evaluation eligibility assessment.

| DataBench answer type | Historical Development | New Validation | New Test |
| --- | ---: | ---: | ---: |
| Boolean | 37 | 10 | 15 |
| Number | 48 | 10 | 15 |
| Category | 24 | 10 | 15 |
| List[category] | 21 | 5 | 7 |
| List[number] | 22 | 5 | 8 |

Boolean/Number/Category/List are exactly balanced in the 100 additions. Gestational has no
official Category tasks, so feasible quotas balance at the split level rather than every table.
Task families are static aggregation, extremum/ranking, predicate/comparison and lookup/selection;
basic/intermediate/advanced difficulty is inferred from question structure, not an official label
or measured difficulty. Original question, answer and type remain untouched. All 252 official
reference self-comparisons pass the pinned scorer. This only verifies format compatibility;
official gold has not been independently adjudicated or corrected.

Duplicate checks mask quoted literals and numeric/date tokens, compare normalized exact text,
and flag token Jaccard >=0.72 plus character SequenceMatcher >=0.84. Olist additionally checks
literal-masked SQL AST templates and authored semantic objective IDs. There are zero new
duplicate candidates, zero cross-split candidates and zero new SQL-template collisions under
these checks. The 54 retained similar pairs are all within historical Development and are
listed in [duplicate-audit.json](../benchmarks/phase2/duplicate-audit.json).
Schema-specific DataBench template fingerprints retain field/measure words: common abstract
operations such as ranking are intentionally shared across schemas. These checks detect
surface/template leakage and do not prove semantic independence; independent semantic review
remains open. No embedding model or candidate Agent was used for screening.

## Registry, reproduction and safe use

[tasks.json](../benchmarks/phase2/tasks.json) is the unified public catalog: task ID, dataset,
database, split, question or withheld marker, question commitment, family, semantic-template
fingerprint, answer type, difficulty, reference locator/commitment, grading rule, source version
and review status. Non-Test gold is separated into `development.references.json` and
`validation.references.json`. Test records omit question text, detailed business contracts,
SQL, gold and rubric text. The complete Test records and gold exist only in ignored local storage.
References, sources, review metadata and construction code stay outside the installed `src/`
agent package and must never be put into the Agent's retrieval context.

The [manifest](../benchmarks/phase2/manifest.json) hashes public files, protected resources and
historical manifests/reports. Public frozen JSON files enforce LF with `.gitattributes` and
their file SHA-256 hashes exact bytes. Historical text hashes normalize CRLF to LF without
rewriting the historical artifacts; binary source files always hash exact bytes. Object commitments hash compact
sorted-key, UTF-8 JSON with `ensure_ascii=False`, `allow_nan=False`, separators `,` and `:`, and
one terminal LF. Logical source-table commitments hash row arrays sorted by that canonical byte
encoding, retaining duplicates. Gold decimals use `{"decimal":"..."}`; floats are rounded to
nine places before freezing. Use the pinned Python 3.12 / project dependencies and benchmark
extras; no network/model credentials are required for public checks.

```sh
python -m pip install -e ".[test,benchmark]"
python -m benchmarks.phase2_registry
python -m pytest -q
```

Dataset access for future Development/Validation workflows:

```python
from benchmarks.phase2_registry import load_tasks
development = load_tasks("development")  # 237; never opens Test resources
validation = load_tasks("validation")    # 60; never opens Test resources
# load_tasks("test") raises before reading any files.
```

These are dataset APIs, not a new Agent experiment runner. Existing `benchmarks.run` and
`benchmarks.databench` commands continue to reproduce historical regression runs with their
original `test`/`dev`/`holdout` aliases. Do not reinterpret those names as Phase II Test.
Historical scores are unchanged. The new row protocol and separate final grader do not rescore
historical outputs.

Full owner-side reconstruction needs the original local Olist ZIP/database, all historical
DataBench raw files at the existing roots, and the restricted Olist Test authoring packet:

```sh
# Prepare historical files with the original three commands if missing.
python -m benchmarks.databench --split test --fetch
python -m benchmarks.databench --split dev --fetch
python -m benchmarks.databench --split holdout --fetch
# Use scripts/fetch_olist.py and scripts/build_olist.py for the unchanged Olist snapshot.
python -m benchmarks.build_phase2 --fetch --olist-test-authoring data/phase2/owner/olist-test-authoring.json
```

The builder verifies frozen source hashes, reconstructs source rows, reruns all reference/duplicate
checks, and writes the same catalog, references and candidate bundle. Public code deliberately
cannot reconstruct Olist Test questions without the owner resource. Reproduction is auditable by
the owner/reviewer with that resource; it is not a public release of Test content. Rebuilding a
freeze must reproduce manifest hashes; changing runtime or content requires a versioned release.
The builder refuses to overwrite changed frozen public/private content under the same release
name. Reviewed corrections require an explicit new `--release` and a documented exposure audit.

## Owner-controlled final evaluation

Current local packet: `data/phase2/owner/` (100 tasks, gold, Olist authoring, handoff note).
The dataset constructor has accessed candidate Test information. Local developer access has not
been revoked, and public IDs allow recovery of upstream DataBench gold. The status is therefore
**`FROZEN_CANDIDATE_NOT_BLIND`**, not a strict blind test. Git ignore rules and CLI guards prevent
accidental publication/workflow access; they are not account permissions or encryption.

The project owner must:

1. Transfer the frozen packet and required pinned databases to access-controlled storage, verify
   every protected/source hash, assign a custodian, and remove the developer/Agent account's access.
   Do not remove the only copy; back up and verify custody before revocation.
2. Arrange independent Olist semantic/reference review and record exposure. If strict blindness
   is required against this constructor or subsequent developers exposed to these questions,
   have a separate curator replace the exposed candidate content and freeze a new release.
   Public upstream questions cannot guarantee freedom from prior model knowledge.
3. Before access to final questions, freeze the selected code commit, model/configuration,
   permitted tools, budgets, scoring rules, task IDs and any exclusion policy. All selection
   uses Development/Validation only; no tuning against Test outcomes.
4. On a separate owner-controlled host, validate the frozen packet and export only question and
   database identity to the locked runner. Gold stays with the grading account. Collect exactly
   one prediction per task and retain outputs privately. Release aggregated results only after
   the final run and independent rubric scoring are complete.

The separate commands below are a future execution plan, **not commands run on a candidate in
this release**. The acknowledgment flag does not create blindness:

```sh
python -m benchmarks.final_phase2 --owner-root <restricted-packet> --acknowledge-candidate-not-blind --export-questions
# Owner runs the previously frozen candidate separately. Predictions are a JSON array:
# {"task_id": "...", "answer": [[cell, ...], ...]} for Olist rows;
# scalar/list for official DataBench; text for rubric tasks.
python -m benchmarks.final_phase2 --owner-root <restricted-packet> --acknowledge-candidate-not-blind --predictions <private-predictions.json>
```

Outputs remain within the owner packet. The grader checks every private question/reference
against public commitments and uses the official scorer for DataBench. Five Olist Test rubric
tasks remain pending human scoring; the CLI reports that gap and never invents an overall
100-task accuracy. The owner must attach criterion-level independent judgments to complete the
final report, retaining the full 100-task denominator and marking omissions as unresolved.

## Delivered checks and remaining gates

The public validator verifies all 397 IDs, 85/20/40 and 152/40/60 counts, retained 197 tasks,
database isolation, source/reference completeness and commitments. Automated tests inject
duplicate IDs, cross-split questions/templates/databases, missing references, accidental Test
text, changed gold commitments, numeric/NULL errors and incomplete final submissions. Public
CI never reads Test gold. Source construction verifies all eight Olist linked row multisets,
88 new SQL references, all official file hashes/IDs and 252 official scorer round-trips. The
machine-readable [audit](../benchmarks/phase2/audit.json) records evidence and limitations.

Local validation on the pinned snapshot: **61 tests passed**, including the three opt-in
source-data checks (`COMMERCE_VERIFY_OLIST_DB=data/olist.duckdb`). A second full owner-packet
reconstruction of candidate v2 reproduced every public/protected file commitment and the complete
manifest byte for byte. The separate owner loader verified all 100 protected task/reference
commitments without executing or grading any candidate Agent. Commands used:

```sh
COMMERCE_VERIFY_OLIST_DB=data/olist.duckdb python -m pytest -q
python -m benchmarks.phase2_registry
python -m benchmarks.build_phase2 --olist-test-authoring data/phase2/owner/olist-test-authoring.json
```

Remaining gates are independent human acceptance of the 145 Olist references, semantic duplicate
review beyond heuristic screening, owner custody/access isolation and a future locked final
evaluation. No candidate Test inference, Test-guided tuning, historical rescoring or main merge
is part of this release. Numerical construction is complete; those review/isolation gates are
explicitly open.
