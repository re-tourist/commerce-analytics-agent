from datetime import date
from decimal import Decimal

import pytest

from commercelens.application.contracts import Investigation, ToolError
from commercelens.infrastructure.analytics.investigation import investigate


def test_rate_eligibility_and_contributions(analytical_data):
    spec = Investigation(
        "late_rate", "customer_state", date(2018, 7, 1), date(2018, 8, 1),
        date(2018, 6, 1), date(2018, 7, 1), 1,
    )
    result = investigate(analytical_data, spec).calculations
    assert (result["current"], result["baseline"], result["delta"]) == (1, Decimal("0.5"), Decimal("0.5"))
    assert result["current_population"] == result["baseline_population"] == 2
    assert result["groups"][0]["group"] == "RJ"
    assert result["groups"][0]["delta_contribution"] + result["omitted_delta_contribution"] == result["delta"]


def test_absent_and_overlapping_periods(analytical_data):
    assert investigate(
        analytical_data, Investigation("order_count", start=date(2025, 1, 1), end=date(2025, 2, 1))
    ).calculations["current"] is None
    with pytest.raises(ToolError, match="Baseline must end"):
        investigate(analytical_data, Investigation(
            "late_rate", start=date(2018, 7, 1), end=date(2018, 8, 1),
            baseline_start=date(2018, 6, 1), baseline_end=date(2018, 7, 2),
        ))


def test_review_comparison_excludes_unknown_delivery_status(analytical_data):
    evidence = investigate(analytical_data, Investigation("review_score", "is_late"))
    assert {row["group"]: row["current_value"] for row in evidence.calculations["groups"]} == {
        "true": 3, "false": Decimal("4.5"),
    }
