# CommerceLens portfolio delivery

| Gate | Status |
| --- | --- |
| Portfolio engineering | `ENGINEERING_COMPLETE` on the stacked review branch. |
| Olist formal benchmark acceptance | `PENDING_HUMAN_REVIEW` in [issue #7](https://github.com/re-tourist/commerce-analytics-agent/issues/7). The audit marks 35 cases `AUTO_VERIFIED` and 10 `REVIEW_REQUIRED`. Zero cases have a human signature. |
| Default branch publication | `NOT_RELEASED`. The remote default branch was checked at `117ffb553530f19afe58993b1e3d6d0b9efe3a01`, an empty tree. |

## Evidence

- The audit rebuilt the 15,000-order sample independently from the pinned archive. All eight linked tables matched and all 36 SQL references agreed with Python reference calculations. Question definitions, the historical grader, and measured results are preserved. [Reviewer instructions](../benchmarks/REVIEW.md)
- A real Chromium run executed the delivery and merchandise examples, the payment comparison, and the unsupported inventory question through the local model. Each report was downloaded and parsed, and the reports contained live model usage and traces. SQL, calculation and citations were present for the quantitative cases. The inventory report carried the unconfirmed question. The README image is an unmodified capture of the delivery run.
- The opt-in real-data regression tests verified both cohort populations and numerators directly against raw Olist SQL, then reconciled retained and omitted group contributions to the aggregate change. Local suite with the real data check enabled passed 35 tests. Standard CI on Windows and Ubuntu runs the dataset-free checks.
- [Showcase and reproduction](../docs/reproduction.md#three-minute-showcase) · [Résumé copy and interview notes](../docs/portfolio.md)

## Review stack

| PR | Current base | Verified head | Diff and current checks |
| --- | --- | --- | --- |
| [#6](https://github.com/re-tourist/commerce-analytics-agent/pull/6) | `main` | `c726c7f435ddabbb247c555e9c146b6085d4c745` | 39 files, creates the project and initial README. Windows and Ubuntu passed. |
| [#9](https://github.com/re-tourist/commerce-analytics-agent/pull/9) | `codex/commercelens-mvp` | `71040c27f72d3d8f5de91eb0e95aab1402e2706a` | 11 files, adds schema grounding and paired DataBench results. Windows and Ubuntu passed. |
| [#10](https://github.com/re-tourist/commerce-analytics-agent/pull/10) | `codex/databench-schema-grounding` | `eef80124a5764835274ec090819705d96f7e9e65` | 10 files, adds semantic audit, ablation and holdout. Windows and Ubuntu passed. |
| Portfolio PR | `codex/databench-semantic-holdout` | See the PR head | Audit, demo and screenshot, documentation and career notes. |

The three parent PRs were open and GitHub reported clean merge states at inspection. M1–M4 remain open. Issues #1–#5 track the MVP stages, #8 tracks the schema experiment, and #7 remains the independent review gate. The stack contains repeated edits to benchmark files, so each child must be reviewed against its new base before merging.

1. Obtain explicit authorization and verify that the recorded heads, branch protection, checks and diff still match the reviewed revisions. Review and merge #6 first to publish the initial README and runnable MVP.
2. Keep the parent branch while retargeting #9 to `main`. Review the child-only diff and wait for Windows and Ubuntu CI on the new base. Repeat for #10 after #9 is merged, then for the portfolio PR after #10.
3. Prefer merge commits if repository settings allow them because they preserve stack ancestry. If squash merging is required, prepare a fresh child branch containing only its child commits on the new base and verify it before replacing the PR. Branch deletion and force-push are outside this handoff.
4. After separately authorized merges, confirm the default branch serves the final README and screenshot and the documented setup passes from a clean checkout. Formal Olist benchmark acceptance additionally requires the independent review record.
