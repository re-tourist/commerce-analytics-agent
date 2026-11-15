import pytest

from commercelens.application.contracts import ToolError
from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB, validate_sql


def test_select_ctes_and_joins(analytical_data):
    result = analytical_data.query("""
        WITH matched AS (SELECT order_id FROM orders WHERE is_late AND customer_state = 'SP')
        SELECT category, count(*) FROM matched JOIN items USING (order_id) GROUP BY category
    """)
    assert result.rows == [["books", 1]]


@pytest.mark.parametrize("statement", [
    "CREATE TABLE new_table AS SELECT * FROM orders",
    "SELECT * FROM internal_notes",
    "SELECT * FROM main.orders",
    "SELECT * FROM orders; SELECT * FROM items",
    "SELECT * FROM orders JOIN range(3) ON true",
    "SELECT current_setting('threads') FROM orders",
    "WITH RECURSIVE example(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM example) SELECT * FROM example",
])
def test_policy_rejects_out_of_scope_sql(statement):
    with pytest.raises(ToolError):
        validate_sql(statement, {"orders", "items"})


def test_readonly_and_external_access_settings(analytical_data):
    with analytical_data.connect() as db:
        assert db.execute("SELECT current_setting('access_mode'), current_setting('enable_external_access'), "
                          "current_setting('lock_configuration')").fetchone() == ("read_only", False, True)


def test_output_cap(analytical_data):
    data = ReadOnlyDuckDB(analytical_data.path, ("orders",), row_limit=2)
    result = data.query("SELECT order_id FROM orders ORDER BY order_id")
    assert result.rows == [["a"], ["b"]]
    assert result.truncated
