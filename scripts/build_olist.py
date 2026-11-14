"""Build a verified, stratified Olist database and provenance manifest."""

import argparse
from collections import Counter
import csv
import hashlib
import heapq
from io import TextIOWrapper
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import duckdb

from fetch_olist import SHA256, SOURCE, checksum


FILES = {
    "orders": "olist_orders_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "categories": "product_category_name_translation.csv",
}

RELATION_SQL = {
    "orders": "SELECT o.* FROM raw_orders o SEMI JOIN chosen USING (order_id)",
    "customers": "SELECT * FROM raw_customers SEMI JOIN source.orders USING (customer_id)",
    "items": "SELECT * FROM raw_items SEMI JOIN chosen USING (order_id)",
    "payments": "SELECT * FROM raw_payments SEMI JOIN chosen USING (order_id)",
    "reviews": "SELECT * FROM raw_reviews SEMI JOIN chosen USING (order_id)",
    "products": "SELECT * FROM raw_products SEMI JOIN source.items USING (product_id)",
    "sellers": "SELECT * FROM raw_sellers SEMI JOIN source.items USING (seller_id)",
    "categories": "SELECT * FROM raw_categories SEMI JOIN source.products USING (product_category_name)",
}

VIEWS = """
CREATE VIEW orders AS
WITH payments AS (
    SELECT order_id, sum(payment_value::DECIMAL(18,2)) AS payment_value
    FROM source.payments GROUP BY order_id
), reviews AS (
    SELECT order_id, avg(review_score::INTEGER) AS review_score
    FROM source.reviews WHERE try_cast(review_score AS INTEGER) BETWEEN 1 AND 5
    GROUP BY order_id
)
SELECT o.order_id, o.order_status, o.order_purchase_timestamp::DATE AS purchase_date,
       c.customer_state, coalesce(p.payment_value, 0) AS payment_value, r.review_score,
       CASE WHEN o.order_status = 'delivered'
                 AND o.order_delivered_customer_date::TIMESTAMP >= o.order_purchase_timestamp::TIMESTAMP
            THEN epoch(o.order_delivered_customer_date::TIMESTAMP - o.order_purchase_timestamp::TIMESTAMP)
                 / 86400.0 END AS delivery_days,
       CASE WHEN o.order_status = 'delivered'
            THEN o.order_delivered_customer_date::DATE > o.order_estimated_delivery_date::DATE END AS is_late
FROM source.orders o JOIN source.customers c USING(customer_id)
LEFT JOIN payments p USING(order_id) LEFT JOIN reviews r USING(order_id);
CREATE VIEW items AS
SELECT i.order_id, i.order_item_id::INTEGER AS order_item_id, i.product_id, i.seller_id,
       o.purchase_date, o.customer_state, s.seller_state,
       coalesce(t.product_category_name_english, p.product_category_name, 'unknown') AS category,
       i.price::DECIMAL(18,2) AS price, i.freight_value::DECIMAL(18,2) AS freight_value
FROM source.items i JOIN orders o USING(order_id)
JOIN source.sellers s USING(seller_id) JOIN source.products p USING(product_id)
LEFT JOIN source.categories t USING(product_category_name);
CREATE TABLE seller_orders AS
WITH participants AS (SELECT DISTINCT order_id, seller_id FROM source.items)
SELECT i.order_id, i.seller_id, s.seller_state, o.purchase_date, o.customer_state, o.is_late
FROM participants i JOIN orders o USING(order_id) JOIN source.sellers s USING(seller_id);
"""


def sample_orders(archive: ZipFile, size: int, seed: int) -> tuple[list[str], dict[str, int], dict[str, int]]:
    with archive.open(FILES["orders"]) as source, TextIOWrapper(source, encoding="utf-8-sig") as stream:
        strata: dict[str, list[str]] = {}
        seen = set()
        for row in csv.DictReader(stream):
            order_id = row["order_id"]
            if order_id in seen or not order_id or not row["order_purchase_timestamp"]:
                raise ValueError("Orders contain duplicate or incomplete sampling keys")
            seen.add(order_id)
            month = row["order_purchase_timestamp"][:7]
            strata.setdefault(month, []).append(order_id)
    total = len(seen)
    if not 0 < size <= total:
        raise ValueError("Sample size must be between 1 and the source order count")
    counts = {month: len(strata[month]) for month in sorted(strata)}
    quotas = {month: size * count // total for month, count in counts.items()}
    remainder = size - sum(quotas.values())
    priority = sorted(counts, key=lambda month: (-(size * counts[month] % total), month))
    for month in priority[:remainder]:
        quotas[month] += 1
    selected = [
        order_id
        for month, quota in quotas.items()
        for order_id in heapq.nsmallest(
            quota, strata[month],
            key=lambda order_id: (hashlib.sha256(f"{seed}:{order_id}".encode()).digest(), order_id),
        )
    ]
    return sorted(selected), counts, quotas


def stage(db: duckdb.DuckDBPyConnection, directory: Path, identifiers: list[str]) -> dict:
    db.execute("CREATE SCHEMA source; CREATE TEMP TABLE chosen(order_id VARCHAR PRIMARY KEY)")
    id_csv = directory / "chosen.csv"
    with id_csv.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows([["order_id"], *((value,) for value in identifiers)])
    db.execute("INSERT INTO chosen SELECT * FROM read_csv(?, header=true, all_varchar=true)", [str(id_csv)])
    for name, filename in FILES.items():
        db.execute(
            f"CREATE TEMP TABLE raw_{name} AS SELECT * FROM read_csv(?, header=true, all_varchar=true)",
            [str(directory / filename)],
        )
    for name, sql in RELATION_SQL.items():
        db.execute(f"CREATE TABLE source.{name} AS {sql}")
    db.execute(VIEWS)
    return validate(db, len(identifiers))


def validate(db: duckdb.DuckDBPyConnection, size: int) -> dict:
    counts = {name: db.execute(f"SELECT count(*) FROM source.{name}").fetchone()[0] for name in FILES}
    edges = [
        ("orders", "customers", "customer_id"),
        ("items", "orders", "order_id"),
        ("items", "products", "product_id"),
        ("items", "sellers", "seller_id"),
        ("payments", "orders", "order_id"),
        ("reviews", "orders", "order_id"),
    ]
    orphans = {
        f"{child}.{column}->{parent}": db.execute(
            f"SELECT count(*) FROM source.{child} ANTI JOIN source.{parent} USING ({column})"
        ).fetchone()[0]
        for child, parent, column in edges
    }
    keys = {
        "orders": "(order_id)", "items": "(order_id, order_item_id)",
        "payments": "(order_id, payment_sequential)", "customers": "(customer_id)",
        "products": "(product_id)", "sellers": "(seller_id)", "categories": "(product_category_name)",
    }
    duplicates = {
        table: db.execute(
            f"SELECT count(*) - count(DISTINCT {key}) FROM source.{table}"
        ).fetchone()[0]
        for table, key in keys.items()
    }
    if counts["orders"] != size or any(orphans.values()) or any(duplicates.values()):
        raise ValueError(f"Sample integrity failed: {counts=}, {orphans=}, {duplicates=}")
    for view in ("orders", "items"):
        if db.execute(f"SELECT count(*) FROM {view}").fetchone()[0] != counts[view]:
            raise ValueError(f"Unexpected join fanout in {view}")
    if db.execute("SELECT count(*) FROM seller_orders").fetchone()[0] != db.execute(
        "SELECT count(DISTINCT (order_id, seller_id)) FROM source.items"
    ).fetchone()[0]:
        raise ValueError("Seller participation grain does not reconcile")
    totals = db.execute("""
        SELECT (SELECT sum(payment_value) FROM orders),
               (SELECT sum(payment_value::DECIMAL(18,2)) FROM source.payments),
               (SELECT sum(price) FROM items),
               (SELECT sum(price::DECIMAL(18,2)) FROM source.items)
    """).fetchone()
    if totals[0] != (totals[1] or 0) or totals[2] != totals[3]:
        raise ValueError("Monetary view totals do not reconcile")
    missing_categories = db.execute("""
        SELECT count(*) FROM source.products ANTI JOIN source.categories USING (product_category_name)
    """).fetchone()[0]
    return {
        "rows": counts, "orphans": orphans, "duplicate_or_null_keys": duplicates,
        "products_without_translation": missing_categories,
        "payment_value_brl": str(totals[0]), "merchandise_value_brl": str(totals[2]),
    }


def build(archive_path: Path, output: Path, size: int = 15_000, seed: int = 741) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    archive_hash = checksum(archive_path)
    if archive_hash != SHA256:
        raise ValueError("Input does not match the pinned Olist v2 archive")
    with TemporaryDirectory(prefix="olist-", dir=output.parent) as scratch, ZipFile(archive_path) as archive:
        directory = Path(scratch)
        selected, counts, quotas = sample_orders(archive, size, seed)
        for filename in FILES.values():
            archive.extract(filename, directory)
        staging = directory / output.name
        with duckdb.connect(str(staging), config={"threads": "1"}) as db:
            stats = stage(db, directory, selected)
            observed = Counter(dict(db.execute("""
                SELECT strftime(purchase_date, '%Y-%m'), count(*) FROM orders GROUP BY 1
            """).fetchall()))
            if observed != Counter(quotas):
                raise ValueError("Observed monthly counts differ from sampling quotas")
        manifest = {
            "source": SOURCE, "version": 2, "archive_sha256": archive_hash,
            "license": "CC BY-NC-SA 4.0", "duckdb_version": duckdb.__version__,
            "sample": {
                "method": "Monthly proportional largest remainder, ties by month; lowest SHA-256(seed:order_id)",
                "seed": seed, "size": size, "source_month_counts": counts, "sample_month_counts": quotas,
                "order_ids_sha256": hashlib.sha256("\n".join(selected).encode()).hexdigest(),
            },
            "checks": stats,
            "database_bytes": staging.stat().st_size,
            "database_sha256": checksum(staging),
        }
        if manifest["database_bytes"] > 100_000_000:
            raise ValueError("Processed database exceeds 100 MB")
        manifest_path = staging.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        staging.replace(output)
        manifest_path.replace(output.with_suffix(".manifest.json"))
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", dest="archive_path", type=Path, default=Path("data/raw/olist-v2.zip"))
    parser.add_argument("--output", type=Path, default=Path("data/olist.duckdb"))
    parser.add_argument("--size", type=int, default=15_000)
    parser.add_argument("--seed", type=int, default=741)
    print(json.dumps(build(**vars(parser.parse_args())), indent=2))
