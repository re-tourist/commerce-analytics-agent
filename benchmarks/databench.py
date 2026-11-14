"""Build and grade the pinned SemEval 2025 Task 8 adapted full-table subset."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlretrieve

import duckdb
import pyarrow.parquet as parquet

from commercelens.infrastructure.data.readonly import encode_value

REVISION = "e75d53add267d2f9cfa32efd65ad77f0807adfad"
TABLES = ("066_IBM_HR", "072_Admissions", "073_Med_Cost", "076_NBA", "079_Coffee")
SEED = 741
PER_TABLE = 16


def selected_cases(root: Path) -> dict:
    result = {}
    for name in TABLES:
        source = root / "raw" / name / "qa.parquet"
        rows = parquet.read_table(source, columns=["dataset", "question", "type", "answer"]).to_pylist()
        if len(rows) < PER_TABLE or any(row["dataset"] != name for row in rows):
            raise ValueError(f"Unexpected official QA rows in {name}")
        for index, row in enumerate(rows):
            row["id"] = f"{name}:{index:03}"
        ranked = sorted(rows, key=lambda row: hashlib.sha256(f"{SEED}:{row['id']}".encode()).digest())
        result[name] = sorted(ranked[:PER_TABLE], key=lambda row: row["id"])
    return result


def prepare(root: Path, fetch: bool) -> None:
    (root / "db").mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/datasets/cardiffnlp/databench/resolve/{REVISION}/data"
    manifest = {}
    for table in TABLES:
        directory = root / "raw" / table
        directory.mkdir(parents=True, exist_ok=True)
        manifest[table] = {"files": {}}
        for filename in ("all.parquet", "qa.parquet"):
            target = directory / filename
            if fetch and not target.exists():
                partial = target.with_suffix(".part")
                try:
                    urlretrieve(f"{base}/{table}/{filename}", partial)
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)
            with target.open("rb") as stream:
                manifest[table]["files"][filename] = hashlib.file_digest(stream, "sha256").hexdigest()
        source = directory / "all.parquet"
        target = root / "db" / f"{table}.duckdb"
        with duckdb.connect(str(target.resolve()), config={"threads": "1"}) as db:
            db.execute("CREATE OR REPLACE TABLE data_table AS SELECT * FROM read_parquet(?)", [str(source)])
            rows = db.execute("SELECT count(*) FROM data_table").fetchone()[0]
        if rows != parquet.read_metadata(source).num_rows:
            raise ValueError(f"Row count mismatch in {table}")
        manifest[table]["rows"] = rows
    for table, cases in selected_cases(root).items():
        manifest[table]["question_ids"] = [row["id"] for row in cases]
    (root / "manifest.json").write_text(json.dumps({
        "source": "https://huggingface.co/datasets/cardiffnlp/databench", "revision": REVISION,
        "track": "SemEval 2025 Task 8 adapted subset (test, full tables)", "seed": SEED,
        "sampling": "Five preselected official test tables; 16 lowest SHA-256(seed:table:row) per table",
        "tables": manifest,
    }, indent=2) + "\n", encoding="utf-8")


def score(answer, case):
    from databench_eval import Evaluator

    evidence = answer.evidence
    table = evidence.result
    valid = answer.tool == "sql" and answer.status in {"ok", "empty"} and table and not table.truncated
    correct = False
    executed = answer.tool == "sql" and table is not None
    semantic = case["type"]
    if valid:
        rows = table.rows
        if semantic.startswith("list["):
            if len(table.columns) == 1:
                value = [row[0] for row in rows]
                if len(value) == 1 and isinstance(value[0], str) and value[0].startswith("["):
                    value = value[0]
                correct = Evaluator.default_compare(None, value, case["answer"], semantic)
        elif len(rows) == 1 and len(rows[0]) == 1:
            value = encode_value(rows[0][0])
            correct = Evaluator.default_compare(None, value, case["answer"], semantic)
    return {
        "success": correct, "tool_correct": answer.tool == "sql", "retrieval_hit": None,
        "citation_precision": None, "numerical_correct": correct if "number" in semantic else None,
        "sql_executed": executed, "sql_correct": correct,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/databench"))
    parser.add_argument("--fetch", action="store_true")
    options = parser.parse_args()
    prepare(options.root, options.fetch)
