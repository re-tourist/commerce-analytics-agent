"""Units, input grain and inclusion rules shared by the graph and analytics."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    name: str
    relation: str
    value: str
    weight: str
    dimensions: tuple[str, ...]
    unit: str
    definition: str
    rate: bool = False


METRICS = {
    "order_count": Metric(
        "Order count", "orders", "1", "1", ("customer_state",), "orders",
        "Count sampled orders of all statuses placed in the purchase window.",
    ),
    "payment_value": Metric(
        "Payment value proxy", "orders", "payment_value", "1", ("customer_state",), "BRL",
        "Sum recorded payments once per sampled order, all statuses. This does not measure net revenue.",
    ),
    "merchandise_value": Metric(
        "Merchandise value proxy", "items", "price", "1",
        ("customer_state", "seller_state", "seller_id", "category"), "BRL",
        "Sum item prices without freight or order payments, all statuses. Missing categories are unknown.",
    ),
    "late_rate": Metric(
        "Late delivery rate", "orders", "CASE WHEN is_late THEN 1 ELSE 0 END",
        "CASE WHEN is_late IS NOT NULL THEN 1 ELSE 0 END",
        ("customer_state",), "share",
        "Among delivered orders with observed and estimated delivery dates, count deliveries after the "
        "estimated calendar date. Purchase month defines the cohort.", True,
    ),
    "seller_late_share": Metric(
        "Seller-order late delivery rate", "seller_orders", "CASE WHEN is_late THEN 1 ELSE 0 END",
        "CASE WHEN is_late IS NOT NULL THEN 1 ELSE 0 END", ("seller_id", "seller_state"), "share",
        "One row per seller and order. A multi-seller order counts once for each participating seller. "
        "Order-level delivery status is shared across sellers and cannot establish seller fault.", True,
    ),
    "delivery_days": Metric(
        "Mean delivery days", "orders", "COALESCE(delivery_days, 0)",
        "CASE WHEN delivery_days IS NOT NULL THEN 1 ELSE 0 END",
        ("customer_state",), "days",
        "Mean elapsed days from purchase to observed delivery for delivered orders with valid timing.", True,
    ),
    "review_score": Metric(
        "Mean order review score", "orders", "COALESCE(review_score, 0)",
        "CASE WHEN review_score IS NOT NULL THEN 1 ELSE 0 END",
        ("customer_state", "is_late"), "stars",
        "Average valid reviews within each order, then average orders with reviews. "
        "Comparisons by late status are observational.", True,
    ),
}

RELATIONS = {
    "orders": "One row per sampled order. Cohort date is purchase_date. Payment and review values are "
              "already aggregated per order; is_late is NULL outside the eligible delivery population.",
    "items": "One row per order item. Use price for seller/category monetary attribution. "
             "Use count(distinct order_id) to count orders within a group.",
    "seller_orders": "One row per order and seller. Order-level lateness can be shared across sellers.",
}
