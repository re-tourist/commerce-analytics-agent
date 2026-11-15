"""End-to-end build checks using a small synthetic archive for clean CI."""

from decimal import Decimal
import hashlib
from importlib import import_module
import json
from pathlib import Path
from zipfile import ZipFile

import duckdb
import pytest


@pytest.fixture
def builder(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return import_module("build_olist")


@pytest.fixture
def archive(tmp_path, builder, monkeypatch):
    path = tmp_path / "synthetic.zip"
    tables = {
        "orders": (
            "order_id,customer_id,order_status,order_purchase_timestamp,"
            "order_delivered_customer_date,order_estimated_delivery_date\n"
            "a,ca,delivered,2018-01-05 12:00:00,2018-01-09 10:00:00,2018-01-08 00:00:00\n"
            "b,cb,canceled,2018-01-06 12:00:00,,2018-01-10 00:00:00\n"
            "c,cc,delivered,2018-01-07 12:00:00,2018-01-08 10:00:00,2018-01-08 00:00:00\n"
            "d,cd,canceled,2018-02-01 12:00:00,,2018-02-05 00:00:00\n"
            "e,ce,delivered,2018-02-02 12:00:00,2018-02-04 10:00:00,2018-02-05 00:00:00\n"
        ),
        "customers": "customer_id,customer_state\nca,SP\ncb,SP\ncc,RJ\ncd,MG\nce,BA\n",
        "items": ("order_id,order_item_id,product_id,seller_id,price,freight_value\n"
                  "a,1,p1,s1,12.00,3.00\na,2,p2,s1,18.00,6.00\nc,1,p1,s2,4.00,4.00\ne,1,p3,s3,99.00,4.00\n"),
        "payments": "order_id,payment_sequential,payment_value\na,1,30.00\na,2,9.00\nc,1,8.00\ne,1,103.00\n",
        "reviews": "order_id,review_score\na,1\na,5\nc,9\ne,4\n",
        "products": "product_id,product_category_name\np1,livros\np2,moveis\np3,excluido\n",
        "sellers": "seller_id,seller_state\ns1,SP\ns2,RJ\ns3,BA\n",
        "categories": "product_category_name,product_category_name_english\nlivros,books\nexcluido,excluded\n",
    }
    with ZipFile(path, "w") as synthetic:
        for name, csv in tables.items():
            synthetic.writestr(builder.FILES[name], csv)
        synthetic.writestr("olist_geolocation_dataset.csv", "unused")
    monkeypatch.setattr(builder, "SHA256", builder.checksum(path))
    return path


def test_build_is_repeatable_and_preserves_grain(archive, builder, tmp_path):
    database = tmp_path / "sample.duckdb"
    first = builder.build(archive, database, size=3)
    second = builder.build(archive, database, size=3)
    assert first["sample"] == second["sample"]
    assert second["sample"]["source_month_counts"] == {"2018-01": 3, "2018-02": 2}
    assert second["sample"]["sample_month_counts"] == {"2018-01": 2, "2018-02": 1}
    assert second["sample"]["order_ids_sha256"] == hashlib.sha256(b"a\nc\nd").hexdigest()
    assert json.loads(database.with_suffix(".manifest.json").read_text(encoding="utf-8")) == second
    assert second["database_sha256"] == builder.checksum(database)
    assert second["checks"]["rows"] == {
        "orders": 3, "customers": 3, "items": 3, "payments": 3, "reviews": 3,
        "products": 2, "sellers": 2, "categories": 1,
    }
    assert second["checks"]["payment_value_brl"] == "47.00"
    assert second["checks"]["merchandise_value_brl"] == "34.00"
    with duckdb.connect(str(database), read_only=True) as db:
        assert db.execute(
            "SELECT order_id, payment_value, is_late, review_score FROM orders ORDER BY order_id"
        ).fetchall() == [
            ("a", Decimal("39.00"), True, 3.0), ("c", Decimal("8.00"), False, None),
            ("d", Decimal("0.00"), None, None),
        ]
        assert db.execute("SELECT count(*) FROM seller_orders").fetchone() == (2,)
        assert db.execute("SELECT DISTINCT category FROM items ORDER BY 1").fetchall() == [("books",), ("moveis",)]
        assert db.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE '%geo%'").fetchall() == []


@pytest.mark.parametrize("payment_sequence", [None, "1"])
def test_payment_keys_reject_missing_or_duplicate_component(archive, builder, tmp_path, payment_sequence):
    database = tmp_path / "sample.duckdb"
    builder.build(archive, database, size=3)
    with duckdb.connect(str(database)) as db:
        db.execute("INSERT INTO source.payments VALUES ('a', ?, '20.00')", [payment_sequence])
        with pytest.raises(ValueError, match=r"duplicates=.*'payments': 1"):
            builder.validate(db, 3)
