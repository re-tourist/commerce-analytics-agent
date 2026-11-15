"""Opt-in checks against raw Olist tables on the actual rebuilt sample."""

from datetime import date
from decimal import Decimal
import os
from pathlib import Path

import duckdb
import pytest

from commercelens.application.contracts import Investigation
from commercelens.bootstrap import olist_data
from commercelens.infrastructure.analytics.investigation import investigate


REFERENCE_QUERIES = {
    "late_rate": """
        SELECT left(order_purchase_timestamp, 7) AS cohort, count(*) AS population,
               count_if(left(order_delivered_customer_date, 10) > left(order_estimated_delivery_date, 10))
        FROM source.orders
        WHERE order_status='delivered' AND order_delivered_customer_date IS NOT NULL
          AND order_estimated_delivery_date IS NOT NULL
        GROUP BY 1
    """,
    "merchandise_value": """
        SELECT left(o.order_purchase_timestamp, 7) AS cohort, count(*) AS population, sum(i.price::DECIMAL(18,2))
        FROM source.items i JOIN source.orders o USING (order_id)
        GROUP BY 1
    """,
    "payment_value": """
        SELECT left(o.order_purchase_timestamp, 7) AS cohort, count(DISTINCT o.order_id) AS population,
               sum(p.payment_value::DECIMAL(18,2))
        FROM source.orders o LEFT JOIN source.payments p USING (order_id)
        GROUP BY 1
    """,
}


@pytest.mark.parametrize(("metric", "dimension"), [
    ("late_rate", "customer_state"), ("merchandise_value", "category"), ("payment_value", "customer_state"),
])
def test_showcase_comparison_matches_independent_source_sql(metric, dimension):
    configured = os.getenv("COMMERCE_VERIFY_OLIST_DB")
    if not configured:
        pytest.skip("Set COMMERCE_VERIFY_OLIST_DB to a locally rebuilt Olist database")
    path = Path(configured).resolve()
    with duckdb.connect(str(path), read_only=True) as db:
        expected = {month: (population, total) for month, population, total
                    in db.execute(REFERENCE_QUERIES[metric]).fetchall()}
    evidence = investigate(olist_data(path), Investigation(
        metric, dimension, date(2018, 7, 1), date(2018, 8, 1), date(2018, 6, 1), date(2018, 7, 1), 8,
    ))
    calc = evidence.calculations
    for label, month in (("baseline", "2018-06"), ("current", "2018-07")):
        population, numerator = expected[month]
        assert (calc[f"{label}_population"], calc[f"{label}_numerator"]) == (population, numerator)
        value = Decimal(numerator) / population if metric == "late_rate" else numerator
        assert calc[label] == value
    contributions = sum(row["delta_contribution"] for row in calc["groups"]) + calc["omitted_delta_contribution"]
    assert abs(contributions - calc["delta"]) < Decimal("1e-12")
