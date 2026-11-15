"""Read-only analytical DuckDB access for model-produced and trusted queries."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
from threading import Timer

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from commercelens.application.contracts import Query, SchemaBindingError, ToolError


FUNCTIONS = set("""
ABS AND APPROX_DISTINCT ARRAY ARRAY_AGG ARRAY_CONCAT ARRAY_SIZE AVG BOOL_AND BOOL_OR CASE CAST
CEIL CEILING COALESCE CONCAT CONCAT_WS CORR COUNT COUNT_IF COVAR_POP CUME_DIST CURRENT_DATE
DATE DATE_ADD DATE_DIFF DATE_PART DATE_TRUNC DATEDIFF DAY DENSE_RANK EPOCH EXTRACT FIRST FIRST_VALUE
FLOOR GREATEST IF IFNULL INITCAP LAG LAST LAST_VALUE LEAD LEAST LEFT LENGTH LIST LIST_AGG LIST_DISTINCT
LIST_SORT LOWER LPAD LTRIM MAX MEDIAN MIN MONTH NULLIF NTILE OR PERCENT_RANK PERCENTILE_CONT
QUANTILE_CONT QUARTER RANK REPLACE RIGHT ROUND ROW_NUMBER RPAD RTRIM SIGN SPLIT_PART SQRT
STDDEV STDDEV_POP STDDEV_SAMP STRFTIME STRING_AGG SUBSTRING SUM TIMESTAMP_TRUNC TRIM TRY_CAST
UPPER VARIANCE VAR_POP VAR_SAMP WEEK YEAR
""".split())


def validate_sql(sql: str, relations: set[str]) -> str:
    if not sql or len(sql) > 8_000:
        raise ToolError("SQL must be nonempty and at most 8,000 characters")
    try:
        statements = sqlglot.parse(sql, read="duckdb")
        if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.SetOperation)):
            raise ToolError("Submit one read-only SELECT query")
        statement = statements[0]
        if statement.find(exp.Into, exp.Lock) or any(cte.args.get("recursive") for cte in statement.find_all(exp.With)):
            raise ToolError("SELECT INTO, locking and recursive CTEs are unavailable")
        for table in statement.find_all(exp.Table):
            if table.db or table.catalog or not isinstance(table.this, exp.Identifier):
                raise ToolError("Use unqualified allowed relations")
        scopes = traverse_scope(statement)
        physical_tables = {
            source.name.casefold()
            for scope in scopes
            for _, source in scope.selected_sources.values()
            if isinstance(source, exp.Table)
        }
        if not physical_tables or physical_tables - relations:
            raise SchemaBindingError("Query must read only from the allowed analytical relations", "relation")
        for node in statement.find_all(exp.Func):
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            if name.upper() not in FUNCTIONS:
                raise ToolError(f"Function unavailable: {name}")
        return statement.sql(dialect="duckdb")
    except SqlglotError as exc:
        raise ToolError("Could not parse or validate SQL") from exc


def encode_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time, timedelta)):
        return str(value)
    if isinstance(value, (tuple, list, dict)):
        return json.dumps(value, default=encode_value, ensure_ascii=False)
    if isinstance(value, float) and (value != value or abs(value) == float("inf")):
        return None
    if isinstance(value, bytes):
        return value.hex()
    return value


class ReadOnlyDuckDB:
    def __init__(self, path: Path, relations: tuple[str, ...], timeout: float = 4, row_limit: int = 200):
        self.path = path.resolve()
        self.relations = relations
        self.timeout = timeout
        self.row_limit = row_limit

    def connect(self):
        if not self.path.is_file():
            raise ToolError("Analytical database is missing. Build the dataset first.")
        return duckdb.connect(str(self.path), read_only=True, config={
            "enable_external_access": "false",
            "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false",
            "threads": "1",
            "memory_limit": "128MB",
            "temp_directory": "",
            "max_temp_directory_size": "0B",
            "lock_configuration": "true",
        })

    def schema(self) -> dict[str, list[tuple[str, str]]]:
        with self.connect() as connection:
            return {
                table: [(row[0], row[1]) for row in connection.execute(
                    'DESCRIBE "' + table.replace('"', '""') + '"'
                ).fetchall()]
                for table in self.relations
            }

    def query(self, sql: str) -> Query:
        sql = validate_sql(sql, set(self.relations))
        with self.connect() as connection:
            timer = Timer(self.timeout, connection.interrupt)
            timer.start()
            try:
                cursor = connection.execute(f"SELECT * FROM ({sql}) AS result LIMIT {self.row_limit + 1}")
                columns = [column[0] for column in cursor.description]
                rows = []
                budget = 100_000
                for raw in cursor.fetchmany(self.row_limit + 1):
                    if len(rows) == self.row_limit:
                        return Query(columns, rows, truncated=True)
                    row = [encode_value(value) for value in raw]
                    budget -= len(json.dumps(row, ensure_ascii=False).encode())
                    if budget < 0:
                        return Query(columns, rows, truncated=True)
                    rows.append(row)
                return Query(columns, rows)
            except duckdb.InterruptException as exc:
                raise ToolError("Query timed out") from exc
            except duckdb.BinderException as exc:
                raise SchemaBindingError("Query failed (BinderException)", "bind") from exc
            except duckdb.Error as exc:
                # Engine exceptions may echo data, file paths or SQL snippets.
                raise ToolError(f"Query failed ({type(exc).__name__})") from exc
            finally:
                timer.cancel()
                timer.join()
