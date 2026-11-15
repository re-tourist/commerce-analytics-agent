"""Audit the pinned Olist cases against independent calculations over the publisher CSVs."""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
from fractions import Fraction
import hashlib
import io
import json
from math import isclose
from pathlib import Path
from zipfile import ZipFile

import duckdb

from benchmarks.olist_cases import cases
from benchmarks.review_olist import SAMPLE_DIGEST
from commercelens.infrastructure.retrieval.knowledge import DOCUMENTS
from scripts.fetch_olist import SHA256, checksum


FILES = {
    "orders": "olist_orders_dataset.csv", "customers": "olist_customers_dataset.csv",
    "items": "olist_order_items_dataset.csv", "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv", "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv", "categories": "product_category_name_translation.csv",
}


def audit(database, archive):
    if checksum(archive) != SHA256:
        raise ValueError("Publisher ZIP hash differs from pinned v2")
    with ZipFile(archive) as source, duckdb.connect(
        str(database.resolve()), read_only=True, config={"enable_external_access": "false"},
    ) as db:
        def records(table, key=None, permitted=None):
            with source.open(FILES[table]) as stream:
                reader = csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
                result = [row for row in reader if key is None or row[key] in permitted]
                columns = ", ".join(f'"{name}"' for name in reader.fieldnames)
            actual = Counter(db.execute(f"SELECT {columns} FROM source.{table}").fetchall())
            if actual != Counter(tuple(v or None for v in row.values()) for row in result):
                raise ValueError(f"Linked records differ from the archive for {table}")
            return result

        with source.open(FILES["orders"]) as stream:
            months = defaultdict(list)
            for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")):
                months[row["order_purchase_timestamp"][:7]].append(row["order_id"])
        total = sum(map(len, months.values()))
        quotas = {m: Fraction(len(ids) * 15000, total) for m, ids in months.items()}
        counts = {m: int(quota) for m, quota in quotas.items()}
        for m in sorted(quotas, key=lambda m: (-(quotas[m] % 1), m))[:15000 - sum(counts.values())]:
            counts[m] += 1
        def rank(identifier):
            return hashlib.sha256(f"741:{identifier}".encode()).hexdigest()

        selected = {identifier for m, ids in months.items()
                    for identifier in sorted(ids, key=rank)[:counts[m]]}
        digest = hashlib.sha256("\n".join(sorted(selected)).encode()).hexdigest()
        if digest != SAMPLE_DIGEST:
            raise ValueError("Archived order IDs differ from the pinned sample")
        orders = {r["order_id"]: r for r in records("orders", "order_id", selected)}
        customers = {r["customer_id"]: r["customer_state"] for r in records(
            "customers", "customer_id", {o["customer_id"] for o in orders.values()})}
        items = records("items", "order_id", selected)
        payments = records("payments", "order_id", selected)
        reviews = records("reviews", "order_id", selected)
        products = {r["product_id"]: r["product_category_name"] for r in records(
            "products", "product_id", {r["product_id"] for r in items})}
        sellers = records("sellers", "seller_id", {r["seller_id"] for r in items})
        translations = {r["product_category_name"]: r["product_category_name_english"] for r in records(
            "categories", "product_category_name", set(products.values()) - {""})}
        cohort = {i: r["order_purchase_timestamp"][:7] for i, r in orders.items()}
        state = {i: customers[r["customer_id"]] for i, r in orders.items()}
        late = {i: o["order_delivered_customer_date"][:10] > o["order_estimated_delivery_date"][:10]
                for i, o in orders.items() if o["order_status"] == "delivered"
                and o["order_delivered_customer_date"] and o["order_estimated_delivery_date"]}
        merchandise = defaultdict(Counter)
        for row in items:
            cat = products[row["product_id"]]
            merchandise[cohort[row["order_id"]]][translations.get(cat) or cat or "unknown"] += Decimal(row["price"])
        paid = Counter()
        for row in payments:
            paid[cohort[row["order_id"]]] += Decimal(row["payment_value"])

        checks = []
        def check(rows, evidence, issue=None):
            checks.append((rows, evidence, issue))
        for month in ("2017-05", "2017-11", "2018-01", "2018-05", "2018-08"):
            check([(counts[month],)], "All sampled orders by purchase month")
            check([(paid[month],)], "Pay each source payment row once, attributed by order purchase month")
            population = [value for identifier, value in late.items() if cohort[identifier] == month]
            check([(Fraction(sum(population), len(population)),)], "Delivered orders with both dates, compared by calendar date")
        for region in ("SP", "RJ", "MG", "BA"):
            matching = {i for i in orders if cohort[i].startswith("2018") and state[i] == region}
            check([(len(matching),)], "Order grain and customer state, all statuses")
            check([(len({row["seller_id"] for row in items if row["order_id"] in matching}),)],
                  "Unique seller IDs across all qualifying item rows")
        for category in ("bed_bath_table", "health_beauty", "sports_leisure", "computers_accessories"):
            check([(sum(values[category] for m, values in merchandise.items() if m.startswith("2018")),)],
                  "Sum item price in translated category, excluding freight")
        for now, prior in (("2018-02", "2018-01"), ("2018-04", "2018-03"), ("2018-06", "2018-05"), ("2018-08", "2018-07")):
            current, baseline = merchandise[now], merchandise[prior]
            changes = sorted(((g, current[g] - baseline[g]) for g in current.keys() | baseline.keys()),
                             key=lambda row: (-abs(row[1]), row[0]))
            issue = "Confirm lexicographic tie-break at the top-three cutoff" if abs(changes[2][1]) == abs(changes[3][1]) else None
            check(changes[:3], "Signed item-price change, outer union of categories, absolute descending", issue)
        delivered = {i: r for i, r in orders.items() if r["order_status"] == "delivered"}
        check([(sum(not r["order_delivered_customer_date"] or r["order_delivered_customer_date"] < r["order_purchase_timestamp"]
                    for r in delivered.values()),)], "Count missing dates or negative delivery duration",
              "Clarify whether a recorded but chronologically invalid delivery is 'no observed duration'")
        check([(sum(cohort[i].startswith("2018") for i in delivered),)], "Delivered status and purchase year")
        scores = defaultdict(list)
        for r in reviews:
            if r["order_id"] in late and 1 <= int(r["review_score"]) <= 5:
                scores[r["order_id"]].append(int(r["review_score"]))
        by_lateness = defaultdict(list)
        for identifier, values in scores.items():
            by_lateness[late[identifier]].append(Fraction(sum(values), len(values)))
        check([(group, sum(values) / len(values)) for group, values in sorted(by_lateness.items())],
              "Average valid reviews within each order, then weight each eligible order equally")
        check([(identifier,) for identifier in sorted(orders) if cohort[identifier].startswith("2025")][:5],
              "Year filter produces no rows on pinned sample")
        check([(sum(s == "XX" for s in state.values()),)], "Customer-state join produces zero matches")

        known_citations = {doc.id for doc in DOCUMENTS}
        output = []
        for case in cases():
            if case.sql:
                expected, evidence, issue = checks[len(output)]
                actual = db.execute(case.sql).fetchall()
                def matches(observed, target):
                    if isinstance(target, Fraction):
                        return isclose(observed, target, rel_tol=1e-12, abs_tol=1e-15)
                    if isinstance(target, bool):
                        return observed is target
                    return observed == target
                if len(actual) != len(expected) or any(
                    len(a) != len(b) or not all(matches(x, y) for x, y in zip(a, b)) for a, b in zip(actual, expected)
                ):
                    raise ValueError(f"Independent calculation disagrees for {case.id}")
            else:
                if set(case.citations) - known_citations:
                    raise ValueError(f"Unknown reference citation for {case.id}")
                evidence = "Citation IDs exist" if case.citations else "Abstention rubric and source schema available in review packet"
                issue = ("Judge whether the cited excerpt fully answers the business question" if case.citations
                         else "Confirm the unavailable evidence and whether an explicitly scoped proxy is acceptable")
            output.append({"id": case.id, "status": "REVIEW_REQUIRED" if issue else "AUTO_VERIFIED",
                           "reference_sql_checked": bool(case.sql), "evidence": evidence, "review": issue})
    return {"archive_sha256": SHA256, "sample_sha256": digest, "orders": len(orders), "source_tables": len(FILES),
            "seller_rows": len(sellers), "status": "PENDING_HUMAN_REVIEW", "cases": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/olist.duckdb"))
    parser.add_argument("--archive", type=Path, default=Path("data/raw/olist-v2.zip"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.db, args.archive)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
