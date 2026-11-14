"""Compare metric cohorts with exact input totals and additive contributions."""

from decimal import Decimal
import json

from commercelens.application.contracts import DataTool, Evidence, Investigation, ToolError
from commercelens.domain.metrics import METRICS


def _periods(spec: Investigation) -> list[tuple[str, str]]:
    if (spec.start is None) != (spec.end is None):
        raise ToolError("Start and end must be supplied together")
    if (spec.baseline_start is None) != (spec.baseline_end is None):
        raise ToolError("Baseline start and end must be supplied together")
    if spec.baseline_start and not spec.start:
        raise ToolError("Baseline comparison requires a current period")
    if spec.start and spec.start >= spec.end:
        raise ToolError("Current period must have positive duration")
    if spec.baseline_start and not spec.baseline_start < spec.baseline_end <= spec.start:
        raise ToolError("Baseline must end at or before the current period starts")

    def condition(start, end):
        return f"purchase_date >= CAST('{start}' AS DATE) AND purchase_date < CAST('{end}' AS DATE)"

    periods = [("current", condition(spec.start, spec.end) if spec.start else "TRUE")]
    if spec.baseline_start:
        periods.append(("baseline", condition(spec.baseline_start, spec.baseline_end)))
    return periods


def investigate(data: DataTool, spec: Investigation) -> Evidence:
    metric = METRICS.get(spec.metric)
    if metric is None:
        raise ToolError("Unknown metric. Use one of: " + ", ".join(METRICS))
    if spec.group and spec.group not in metric.dimensions:
        raise ToolError("Grouping is unavailable for this metric")
    if not 1 <= spec.limit <= 25:
        raise ToolError("Choose a group limit from 1 to 25")
    periods = _periods(spec)
    group = f"COALESCE(CAST({spec.group} AS VARCHAR), 'unknown')" if spec.group else "'all'"
    eligibility = " AND is_late IS NOT NULL" if spec.metric == "review_score" and spec.group == "is_late" else ""
    statements = [
        f"SELECT '{period}' AS period, {group} AS segment, "
        f"COALESCE(SUM({metric.value}), 0) AS numerator, COALESCE(SUM({metric.weight}), 0) AS population "
        f"FROM {metric.relation} WHERE {condition}{eligibility}" + (" GROUP BY 2" if spec.group else "")
        for period, condition in periods
    ]
    # Aggregate before taking the display top N. The lists retain all groups for reconciliation.
    aggregate_sql = " UNION ALL ".join(statements)
    sql = (
        "SELECT period, LIST(numerator ORDER BY segment) AS numerators, "
        "LIST(population ORDER BY segment) AS populations, LIST(segment ORDER BY segment) AS segments "
        f"FROM ({aggregate_sql}) AS grouped GROUP BY period ORDER BY period"
    )
    result = data.query(sql)
    if result.truncated:
        raise ToolError("Grouped evidence exceeded the result budget. Narrow the time window.")
    groups = {period: {} for period, _ in periods}
    for period, numerators, populations, segments in result.rows:
        for segment, numerator, population in zip(
            json.loads(segments), json.loads(numerators, parse_float=Decimal),
            json.loads(populations, parse_float=Decimal), strict=True,
        ):
            groups[period][segment] = (Decimal(str(numerator)), Decimal(str(population)))
    totals = {
        period: (sum((row[0] for row in values.values()), Decimal(0)),
                 sum((row[1] for row in values.values()), Decimal(0)))
        for period, values in groups.items()
    }

    def value(pair):
        numerator, denominator = pair
        return None if not denominator else numerator / denominator if metric.rate else numerator

    comparison = "baseline" in groups
    empty = (Decimal(0), Decimal(0))
    current = value(totals["current"])
    baseline = value(totals.get("baseline", empty))
    delta = current - baseline if comparison and current is not None and baseline is not None else None
    entries = []
    current_groups = groups["current"]
    baseline_groups = groups.get("baseline", {})
    if spec.group:
        for name in sorted(current_groups.keys() | baseline_groups.keys()):
            now = current_groups.get(name, empty)
            before = baseline_groups.get(name, empty)
            contribution = None
            if delta is not None:
                if metric.rate:
                    contribution = now[0] / totals["current"][1] - before[0] / totals["baseline"][1]
                else:
                    contribution = now[0] - before[0]
            entries.append({
                "group": name, "current_value": value(now), "baseline_value": value(before),
                "current_numerator": now[0], "current_population": now[1],
                "baseline_numerator": before[0] if comparison else None,
                "baseline_population": before[1] if comparison else None,
                "delta_contribution": contribution,
            })
        if delta is not None:
            entries.sort(key=lambda item: -abs(item["delta_contribution"]))
        else:
            entries.sort(key=lambda item: (item["current_value"] is None, -(item["current_value"] or 0)))
    retained = entries[:spec.limit]
    omitted_contribution = None
    if delta is not None and spec.group:
        omitted_contribution = sum((item["delta_contribution"] for item in entries[spec.limit:]), Decimal(0))
    calculation = {
        "metric": spec.metric, "definition": metric.definition, "unit": metric.unit,
        "group_by": spec.group, "current": current, "baseline": baseline, "delta": delta,
        "current_population": totals["current"][1],
        "baseline_population": totals["baseline"][1] if comparison else None,
        "groups": retained, "omitted_groups": max(len(entries) - spec.limit, 0),
        "omitted_delta_contribution": omitted_contribution,
        "windows": {
            "current": [spec.start, spec.end],
            "baseline": [spec.baseline_start, spec.baseline_end] if comparison else None,
        },
    }
    return Evidence(sql=sql, result=result, calculations=calculation)
