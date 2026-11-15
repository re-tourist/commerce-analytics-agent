# Olist reference review

Phase II adds 100 questions: 88 source-SQL references marked `AUTO_VERIFIED` and 12
rubric-based references marked `PENDING_HUMAN_REVIEW`. None is independently human-approved.
All 45 historical questions below retain their formal pending review status. See
[the current dataset specification](../docs/BENCHMARKS.md) for split ownership, the protected
candidate Test review packet, and the independent review record required before acceptance.
`AUTO_VERIFIED` verifies computation and source consistency, not business interpretation.

Automated checks verified that reference SQL executes on the pinned sample and that the two demo totals reconcile to source records. The checks used the logical sample with order ID SHA-256 `93e5d327a4b40f9017d09c0e1648f0142fbc499fac7e2217816d2edde7dce175`.

## Human review

Status: `PENDING_HUMAN_REVIEW`. Independent human review remains a gate for formal Olist benchmark acceptance. Engineering and experiments may proceed while the review is open. No case has been signed off by an independent human reviewer.

The [per-case audit](../reports/olist-reference-audit.json) records 35 `AUTO_VERIFIED` and 10 `REVIEW_REQUIRED`. All 36 SQL references agree with independent Python calculations over the publisher ZIP. Start with O032 (missing versus invalid duration), O037–O040 (abstention or proxy), and O041–O045 (citation sufficiency). `AUTO_VERIFIED` means machine checks passed. `HUMAN_APPROVED` requires a named independent reviewer. All 45 remain in scope for formal review.

Record reviewer, date, sample digest, case IDs, discrepancies, corrected references and the run used for retesting in the review on the MVP PR.

Generate the local review packet after building Olist. It verifies the pinned order ID digest and includes the question, reference SQL and computed rows, abstention rubric or nominated knowledge excerpt for all 45 cases. Keep the generated packet in ignored local storage. Share only reviewer findings and case IDs in the PR.

```sh
python -m benchmarks.audit_olist --output reports/olist-reference-audit.json
python -m benchmarks.review_olist
```

The audit independently reconstructs proportional monthly quotas and ranks, then compares the row multisets of all eight linked tables. It uses exact arithmetic for amounts and counts and Fraction-based cross-checks for rates and per-order review averages. The historical grader uses a relative tolerance of 1e-6 for numeric values, which can allow discrepancies larger than one cent for large sums. The existing scoring protocol, case wording and measured results are preserved. If tightening this tolerance is approved, publish a separately versioned report from rescoring the preserved outputs.

| Cases | Verify against source records |
| --- | --- |
| O001–O015 | Purchase windows, all-status counts and payments, and the eligible delivery denominator. |
| O016–O027 | Customer state join, distinct sellers, category translation and item-price grain. |
| O028–O031 | Signed group change, absolute ordering, tie rule and full-month inclusion. |
| O032–O036 | Missing delivery durations, delivered status, review averaging, empty cohort and zero count. |
| O037–O040 | Required unavailable fields and causal evidence. |
| O041–O045 | Cited excerpts answer the question, including grain and population where applicable. |

## Recorded correction

The first model run proposed last-of-month exclusive bounds in the investigation tool. Direct source SQL showed a sign reversal in the showcase merchandise comparison. The agent's calendar interpretation was corrected and the cases rerun. The reference grouping and time windows remained the same.

Preparing the review packet uncovered that O036 used a literal zero as its reference. It now counts matching raw orders through the customer join. The current pinned sample still returns zero. The prior model outputs can be checked for scoring parity without another model run.
