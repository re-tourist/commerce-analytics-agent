# Audit of the 33 executable DataBench mismatches

Source is PR #9's `full_schema_grounded` arm, measured at `69833ff` on the previously exposed 80-case test subset. Primary category assigns each scored mismatch once. Secondary issues appear in the diagnosis where applicable. The unit of analysis is the final SQL result, compared with the question and the pinned reference. The official grading outcome is preserved. The audit does not include the four tool failures.

| Primary category | Cases | Meaning |
| --- | ---: | --- |
| Boolean semantics | 17 | A count, statistic, or intermediate comparison operands were returned instead of a predicate. |
| Projection | 6 | Correct target values appeared with extra columns. |
| Metric or column mapping | 2 | SQL selected a different business measure. |
| Filter or population | 2 | Incorrect eligible rows or stored filter values. |
| Ranking | 2 | Ordered by the wrong measure, direction, or group. |
| Aggregation grain | 1 | Combined multiple seasons for the same player. |
| Numeric type or grading boundary | 3 | Lexical currency order in two cases and a comparator precision boundary in one case. |

There were no observed JOIN-grain errors in these single-table tasks. The player-season grain error is an aggregation issue. One filter used the wrong stored weekday representation. This review found no timestamp or date-window boundary mismatch.

| Case | Primary category | Diagnosis |
| --- | --- | --- |
| 066_IBM_HR:003 | Boolean semantics | Returns maximum daily rate without testing whether it is negative. |
| 066_IBM_HR:005 | Boolean semantics | Returns the maximum rating after restricting to the target rating. The restriction also loses the ability to disprove a higher maximum. |
| 066_IBM_HR:007 | Boolean semantics | Returns two cohort averages without comparing them. The UNION also discards labels and duplicates. |
| 066_IBM_HR:010 | Projection | Correct department with an extra average-tenure column. |
| 066_IBM_HR:013 | Projection | Correct travel category with an extra average-income column. |
| 066_IBM_HR:014 | Projection | Correct gender with an extra mean-satisfaction column. |
| 066_IBM_HR:038 | Projection | Correct job levels with extra counts. |
| 072_Admissions:000 | Boolean semantics | Counts matches instead of evaluating whether one exists. |
| 072_Admissions:003 | Boolean semantics | Counts applicants matching both filters instead of returning existence. |
| 072_Admissions:004 | Boolean semantics | Counts applicants above the probability threshold instead of returning existence. |
| 072_Admissions:007 | Boolean semantics | Returns average score and applies the comparison to input rows. The correct threshold belongs after aggregation. |
| 072_Admissions:036 | Metric or column mapping | Projects two exam scores instead of the statement-of-purpose score for the selected applicants. |
| 073_Med_Cost:000 | Boolean semantics | Counts individuals above the BMI threshold instead of returning existence. |
| 073_Med_Cost:001 | Boolean semantics | Counts distinct regions without comparing the count with the threshold. |
| 073_Med_Cost:002 | Boolean semantics | Returns a count instead of establishing absence. Its equality filter also excludes ages above 100. |
| 073_Med_Cost:003 | Boolean semantics | Computes an average after dropping obese rows. The question asks to compare the population average with the obesity threshold. |
| 073_Med_Cost:005 | Boolean semantics | Counts nonsmokers instead of returning existence. |
| 073_Med_Cost:014 | Boolean semantics | Returns count and share without determining whether this group is most frequent. |
| 073_Med_Cost:021 | Numeric type or grading boundary | The raw sum rounds to the published answer at two decimals. The evaluator's float multiplication and truncation distinguishes the unrounded sum from the two-decimal reference. This is grading sensitivity, rather than evidence of a materially wrong sum. |
| 073_Med_Cost:029 | Filter or population | Filters by number of children instead of the teenage age range, changing which rows qualify. |
| 076_NBA:002 | Boolean semantics | Returns a count instead of existence. The equality filter also admits zero attempts. |
| 076_NBA:003 | Boolean semantics | Returns zero instead of the boolean false. |
| 076_NBA:017 | Metric or column mapping | Uses total rebounds filtered to zero turnovers. Offensive rebounds reconcile to the reference. Interpreting the wording as offensive rebounds is an inferred mapping. |
| 076_NBA:019 | Ranking | Maximizes number of games instead of selecting by minutes and returning the games from that row. |
| 076_NBA:024 | Aggregation grain | Groups by player across seasons and includes player names. The target is rebound totals per player-season. |
| 076_NBA:031 | Projection | Correct team list with extra points totals. |
| 079_Coffee:002 | Boolean semantics | Counts distinct products without comparing against the number of rows. |
| 079_Coffee:005 | Boolean semantics | Returns a count and introduces an ID filter. The threshold applies to the full row count. |
| 079_Coffee:010 | Ranking | Sorts individual transactions descending instead of aggregating revenue by weekday and finding the minimum. The stored revenue also needs numeric conversion. |
| 079_Coffee:011 | Numeric type or grading boundary | Orders the localized currency text lexically. Numeric ordering recovers the reference product type. |
| 079_Coffee:021 | Filter or population | Filters for the full weekday name although values are abbreviated. It also sums quantities instead of counting transactions. |
| 079_Coffee:027 | Projection | Correct four prices with an extra product ID column. |
| 079_Coffee:028 | Numeric type or grading boundary | Lexical ordering and currency text output both conflict with the numeric revenue list. |

Rechecks against the source tables confirmed the stored weekday representations, numeric currency ordering, the source charge sum, the selected NBA minutes row, and the offensive rebound total. These checks explain the archived outcomes. They were separate from model execution and did not change the scorer.

## Candidate

The first candidate is a single opt-in semantic instruction in the SQL planning prompt. It asks the model to identify the measure, population, grain and answer type, then produce the requested predicate or final answer field. These instructions apply across schemas and require no extra model call, no gold metadata, and no SQL-policy exceptions. They directly address the two largest categories, 23/33 combined. This count is the potential scope of the intervention. It does not estimate how many failures the change will fix. Domain-specific metric mappings and currency parsing remain unresolved by this design.
