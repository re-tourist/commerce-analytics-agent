"""Development-only single-table Analysis Plan and DuckDB compiler."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlglot import exp

from commercelens.application.agent.graph import quote_identifier


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Comparison(StrictModel):
    op: Literal["=", "!=", "<", "<=", ">", ">="]
    value: str | int | float | bool

    def sql(self, expression: str) -> str:
        return f"{expression} {self.op} {exp.convert(self.value).sql(dialect='duckdb')}"


class Filter(Comparison):
    column: str


class Aggregate(StrictModel):
    function: Literal["count", "sum", "avg", "min", "max", "median", "stddev_samp", "stddev_pop"]
    column: str | None = None
    distinct: bool = False

    def sql(self, identifier) -> str:
        if self.column is None and (self.function != "count" or self.distinct):
            raise ValueError("Only count can aggregate all rows")
        argument = "*" if self.column is None else identifier(self.column)
        return f"{self.function.upper()}({'DISTINCT ' if self.distinct else ''}{argument})"


class Ordering(StrictModel):
    by: Literal["projection", "aggregate"]
    direction: Literal["asc", "desc"]


class AnalysisPlan(StrictModel):
    kind: Literal["boolean", "scalar", "list", "unsupported"]
    projection: str | None = None
    aggregate: Aggregate | None = None
    filters: list[Filter] = Field(default_factory=list, max_length=8)
    group_by: list[str] = Field(default_factory=list, max_length=4)
    compare: Comparison | None = None
    order: Ordering | None = None
    limit: int | None = Field(default=None, ge=1, le=200)
    distinct: bool = False


def compile_sql(plan: AnalysisPlan, relation: str, columns: set[str]) -> str:
    def identifier(column: str) -> str:
        if column not in columns:
            raise ValueError("Unknown column in analysis plan")
        return quote_identifier(column)

    aggregate = plan.aggregate.sql(identifier) if plan.aggregate else None
    field = identifier(plan.projection) if plan.projection is not None else None
    source = f" FROM {quote_identifier(relation)}"
    if plan.filters:
        source += " WHERE " + " AND ".join(item.sql(identifier(item.column)) for item in plan.filters)

    if plan.kind == "boolean":
        if field or plan.group_by or plan.order or plan.limit or plan.distinct:
            raise ValueError("Boolean plans describe existence or a scalar aggregate comparison")
        if aggregate and plan.compare:
            return f"SELECT {plan.compare.sql(aggregate)} AS answer{source}"
        if not aggregate and not plan.compare:
            return f"SELECT COUNT(*) > 0 AS answer{source}"
        raise ValueError("A boolean aggregate needs a comparison")

    if plan.kind == "unsupported" or plan.compare:
        raise ValueError("Only boolean plans can compare an aggregate")
    if field and aggregate and not plan.order:
        raise ValueError("A non-projected aggregate must be used to rank")
    if plan.group_by and (not aggregate or (field and plan.projection not in plan.group_by)):
        raise ValueError("Grouping requires an aggregate and any projected field in the grouping keys")
    if field and aggregate and not plan.group_by:
        raise ValueError("Ranking fields by an aggregate requires explicit grouping")
    if plan.distinct and (not field or plan.group_by):
        raise ValueError("Distinct projection is limited to ungrouped fields")
    if plan.kind == "scalar" and (field or plan.group_by) and (plan.limit != 1 or not plan.order):
        raise ValueError("A scalar selection of rows or groups requires ordering and a limit of one")
    projection = field or aggregate
    if projection is None:
        raise ValueError("A projection or aggregate is required")
    sql = f"SELECT {'DISTINCT ' if plan.distinct else ''}{projection} AS answer{source}"
    if plan.group_by:
        sql += " GROUP BY " + ", ".join(map(identifier, plan.group_by))
    if plan.order:
        order = aggregate if plan.order.by == "aggregate" else projection
        if order is None:
            raise ValueError("Aggregate ordering requires an aggregate")
        sql += f" ORDER BY {order} {plan.order.direction.upper()}"
    if plan.limit is not None:
        sql += f" LIMIT {plan.limit}"
    return sql


PROMPT = """Translate the question into one JSON analysis plan for the single table below.
Use exact column names, without SQL syntax. Emit only keys needed for the question.
Required kind: "boolean", "scalar", "list", or "unsupported".
Optional keys and shapes:
- projection: name of the single requested output column.
- aggregate: {"function":"count|sum|avg|min|max|median|stddev_samp|stddev_pop",
  "column":"exact column name","distinct":false}. Omit column only to count rows.
- filters: [{"column":"exact name","op":"=|!=|<|<=|>|>=","value":42}]. Filters describe eligible
  input rows and are ANDed. Values must be JSON strings, numbers, or booleans.
- group_by: ["exact name"]. Group only when the question ranks or aggregates groups.
- compare: {"op":"=|!=|<|<=|>|>=","value":42}. Compare a computed aggregate for a boolean answer.
- order: {"by":"projection|aggregate","direction":"asc|desc"}, limit: integer, distinct: boolean.
Boolean with only filters checks existence. Use aggregate and compare for aggregate comparisons.
Scalar aggregate without grouping returns one value. Scalar field or group selection requires
ordering and limit 1. For top groups, project the requested field, group by it and order by the
aggregate. For top rows, project the requested field and order by that same field. When the
request cannot be represented by this grammar, emit {"kind":"unsupported"}.
"""
