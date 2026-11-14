"""Independent Olist references use raw source tables, not production analytical views."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    family: str
    question: str
    sql: str = ""
    metric: str = ""
    citations: tuple[str, ...] = ()
    ordered: bool = False


def window(month: str, alias: str = "o") -> str:
    return f"starts_with({alias}.order_purchase_timestamp, '{month}')"


def cases() -> list[Case]:
    result = []

    def add(family, question, sql="", metric="", citations=(), ordered=False):
        result.append(Case(f"O{len(result) + 1:03d}", family, question, sql, metric, citations, ordered))

    for month in ("2017-05", "2017-11", "2018-01", "2018-05", "2018-08"):
        add("aggregate", f"How many orders were placed in {month} across all statuses? Return one count.",
            f"SELECT count(*) FROM source.orders o WHERE {window(month)}", "order_count")
        add("payment", f"What was the total recorded payment value in BRL for orders purchased in {month}?",
            "SELECT sum(cast(p.payment_value AS DECIMAL(18,2))) FROM source.payments p "
            f"JOIN source.orders o ON p.order_id=o.order_id WHERE {window(month)}", "payment_value")
        add("delivery", f"What fraction of eligible orders purchased in {month} arrived late? Return a 0–1 fraction.",
            "SELECT avg((left(order_delivered_customer_date,10)>left(order_estimated_delivery_date,10))::INT) "
            "FROM source.orders o WHERE order_status='delivered' "
            f"AND order_delivered_customer_date IS NOT NULL AND {window(month)}", "late_rate")

    for state in ("SP", "RJ", "MG", "BA"):
        add("join", f"How many orders were purchased in 2018 by customers in {state}, all statuses?",
            "SELECT count(*) FROM source.orders o INNER JOIN source.customers c "
            f"ON o.customer_id=c.customer_id WHERE c.customer_state='{state}' AND {window('2018')}")
        add("join", f"How many distinct sellers served orders purchased by customers in {state} during 2018?",
            "SELECT count(DISTINCT i.seller_id) FROM source.items i JOIN source.orders o ON i.order_id=o.order_id "
            f"JOIN source.customers c ON o.customer_id=c.customer_id WHERE c.customer_state='{state}' "
            f"AND {window('2018')}")

    for category in ("bed_bath_table", "health_beauty", "sports_leisure", "computers_accessories"):
        add("category", f"Total merchandise value (item price excluding freight) for {category} in 2018, in BRL?",
            "SELECT sum(i.price::DECIMAL(18,2)) FROM source.items i JOIN source.orders o ON i.order_id=o.order_id "
            "JOIN source.products p ON i.product_id=p.product_id JOIN source.categories t "
            f"ON p.product_category_name=t.product_category_name WHERE t.product_category_name_english='{category}' "
            f"AND {window('2018')}")

    for current, baseline in (("2018-02", "2018-01"), ("2018-04", "2018-03"),
                              ("2018-06", "2018-05"), ("2018-08", "2018-07")):
        add("contribution",
            f"Compare {current} versus {baseline} merchandise value. Which top 3 categories contributed most by "
            "absolute change? Return category and signed current-minus-baseline change in BRL.",
            "WITH price_change AS (SELECT coalesce(t.product_category_name_english,p.product_category_name,'unknown') "
            "AS category, SUM(i.price::DECIMAL(18,2) * CASE WHEN "
            f"{window(current)} THEN 1 ELSE -1 END) AS delta "
            "FROM source.orders o JOIN source.items i ON i.order_id=o.order_id "
            "JOIN source.products p ON i.product_id=p.product_id LEFT JOIN source.categories t "
            f"ON p.product_category_name=t.product_category_name WHERE {window(current)} OR {window(baseline)} "
            "GROUP BY 1) SELECT category,delta FROM price_change ORDER BY abs(delta) DESC, category LIMIT 3",
            "merchandise_value", ordered=True)

    add("delivery", "How many delivered orders in the sample have no observed customer delivery duration?",
        "SELECT count(*) FROM source.orders WHERE order_status='delivered' AND "
        "(order_delivered_customer_date IS NULL OR order_delivered_customer_date < order_purchase_timestamp)")
    add("delivery", "How many delivered orders were placed in the sample in 2018?",
        f"SELECT count(*) FROM source.orders o WHERE {window('2018')} AND order_status='delivered'")
    add("review", "Among orders with a review score and eligible delivery status, return lateness (boolean) and "
        "mean per-order review score, ordered false first.",
        "WITH r AS (SELECT order_id, avg(review_score::INTEGER) AS score FROM source.reviews GROUP BY order_id) "
        "SELECT left(o.order_delivered_customer_date,10)>left(o.order_estimated_delivery_date,10) AS late, "
        "avg(score) FROM source.orders o JOIN r ON o.order_id=r.order_id WHERE o.order_status='delivered' "
        "AND o.order_delivered_customer_date IS NOT NULL AND o.order_estimated_delivery_date IS NOT NULL "
        "GROUP BY 1 ORDER BY 1", ordered=True)
    add("empty", "Return the IDs of up to five orders purchased in 2025 in the sample.",
        "SELECT order_id FROM source.orders o WHERE " + window("2025") + " ORDER BY order_id LIMIT 5")
    add("empty", "How many orders have customer state XX?",
        "SELECT count(*) FROM source.orders o JOIN source.customers c ON o.customer_id=c.customer_id "
        "WHERE c.customer_state='XX'")
    for question in (
        "What was aggregate profit margin after cost of goods sold in 2018?",
        "Which warehouse had the highest inventory shortage in July 2018?",
        "How much did changing the carrier causally reduce lateness in SP?",
        "Which refund reason accounted for the highest total refunds?",
    ):
        add("unsupported", question)
    for question, citation in (
        ("Define late delivery rate and its eligible denominator.", "delivery-eligibility"),
        ("What is the difference between order payment and net revenue? Define the metric.", "payment-grain"),
        ("Explain seller attribution when a late order contains several sellers.", "seller-attribution"),
        ("Define the merchandise value metric for product categories.", "category-value"),
        ("How are group contributions to a rate change calculated?", "change-contribution"),
    ):
        add("knowledge", question, citations=(citation,))
    return result
