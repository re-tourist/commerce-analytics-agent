from pathlib import Path

import duckdb
import pytest

from benchmarks.typed_analysis import AnalysisPlan, compile_sql
from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB


@pytest.fixture
def data(tmp_path: Path) -> ReadOnlyDuckDB:
    path = tmp_path / "typed.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("""CREATE TABLE data_table AS SELECT * FROM (VALUES
            ('a', 3), ('a', 4), ('b', 6), ('rare''s item', 30)
        ) AS rows(item, "Unit Value")""")
    return ReadOnlyDuckDB(path, ("data_table",))


@pytest.mark.parametrize(("plan", "expected"), [
    ({"kind": "boolean", "filters": [{"column": "Unit Value", "op": ">", "value": 100}]}, [[False]]),
    ({"kind": "boolean", "aggregate": {"function": "avg", "column": "Unit Value"},
      "compare": {"op": ">", "value": 10}}, [[True]]),
    ({"kind": "list", "projection": "item", "aggregate": {"function": "sum", "column": "Unit Value"},
      "group_by": ["item"], "order": {"by": "aggregate", "direction": "desc"}, "limit": 2},
     [["rare's item"], ["a"]]),
    ({"kind": "scalar", "aggregate": {"function": "sum", "column": "Unit Value"},
      "filters": [{"column": "item", "op": "=", "value": "rare's item"}]}, [[30]]),
])
def test_compiler_preserves_boolean_projection_grain_and_literals(data, plan, expected):
    query = data.query(compile_sql(AnalysisPlan.model_validate(plan), "data_table", {"item", "Unit Value"}))
    assert query.columns == ["answer"]
    assert query.rows == expected


@pytest.mark.parametrize("plan", [
    {"kind": "list", "projection": "missing"},
    {"kind": "list", "projection": "item", "aggregate": {"function": "count"},
     "order": {"by": "aggregate", "direction": "desc"}},
    {"kind": "scalar", "projection": "item"},
])
def test_compiler_rejects_unknown_fields_and_implicit_grain(plan):
    with pytest.raises(ValueError):
        compile_sql(AnalysisPlan.model_validate(plan), "data_table", {"item", "Unit Value"})
