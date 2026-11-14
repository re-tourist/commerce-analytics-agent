from pathlib import Path

import duckdb
import pytest

from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB


@pytest.fixture
def analytical_data(tmp_path: Path):
    path = tmp_path / "fixture.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("""
            CREATE TABLE orders AS SELECT * FROM (VALUES
                ('a', DATE '2018-06-01', 'SP', true, 3.0, 100.00::DECIMAL(18,2), 'delivered'),
                ('b', DATE '2018-06-30', 'SP', false, 5.0, 50.00::DECIMAL(18,2), 'delivered'),
                ('c', DATE '2018-07-01', 'RJ', true, 1.0, 20.00::DECIMAL(18,2), 'delivered'),
                ('d', DATE '2018-07-02', 'RJ', NULL, NULL, 80.00::DECIMAL(18,2), 'canceled'),
                ('e', DATE '2018-07-31', 'SP', true, 5.0, 25.00::DECIMAL(18,2), 'delivered'),
                ('f', DATE '2018-08-01', 'SP', false, 4.0, 900.00::DECIMAL(18,2), 'delivered')
            ) AS t(order_id, purchase_date, customer_state, is_late, review_score, payment_value, order_status);
            CREATE TABLE items AS SELECT 'a' AS order_id, 'books' AS category;
            CREATE TABLE internal_notes AS SELECT 'fixture' AS note;
        """)
    return ReadOnlyDuckDB(path, ("orders", "items"))
