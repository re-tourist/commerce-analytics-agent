"""Build and grade the pinned SemEval 2025 Task 8 adapted full-table subset."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlretrieve

import duckdb
import pyarrow.parquet as parquet

from commercelens.infrastructure.data.readonly import encode_value

DOCS = Path(__file__).resolve().parents[1] / "docs"
SUBSET_FILES = {"test": "databench-subset.json", "dev": "databench-dev-subset.json"}
SUBSET_ROOTS = {"test": Path("data/databench"), "dev": Path("data/databench-dev")}


def pinned_manifest(split: str) -> dict:
    return json.loads((DOCS / SUBSET_FILES[split]).read_text(encoding="utf-8"))


def verify_hash(file: Path, expected: str) -> None:
    with file.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"{file.parent.name}/{file.name} does not match the pinned official SHA-256")


def selected_cases(root: Path, split: str = "test") -> dict:
    pinned = pinned_manifest(split)
    seed = pinned["seed"]
    result = {}
    for name, reference in pinned["tables"].items():
        source = root / "raw" / name / "qa.parquet"
        verify_hash(source, reference["files"]["qa.parquet"])
        question_ids = reference["question_ids"]
        rows = parquet.read_table(source, columns=["dataset", "question", "type", "answer"]).to_pylist()
        if len(rows) < len(question_ids) or any(row["dataset"] != name for row in rows):
            raise ValueError(f"Unexpected official QA rows in {name}")
        for index, row in enumerate(rows):
            row["id"] = f"{name}:{index:03}"
        ranked = sorted(rows, key=lambda row: hashlib.sha256(f"{seed}:{row['id']}".encode()).digest())
        result[name] = sorted(ranked[:len(question_ids)], key=lambda row: row["id"])
        ids = [row["id"] for row in result[name]]
        if ids != question_ids:
            raise ValueError(f"Selected question IDs differ from the pinned manifest for {name}")
    return result


def prepare(root: Path, fetch: bool, split: str = "test") -> None:
    (root / "db").mkdir(parents=True, exist_ok=True)
    pinned = pinned_manifest(split)
    base = f"{pinned['source']}/resolve/{pinned['revision']}/data"
    for table, reference in pinned["tables"].items():
        directory = root / "raw" / table
        directory.mkdir(parents=True, exist_ok=True)
        for filename, digest in reference["files"].items():
            target = directory / filename
            if fetch and not target.exists():
                partial = target.with_suffix(".part")
                try:
                    urlretrieve(f"{base}/{table}/{filename}", partial)
                    partial.replace(target)
                finally:
                    partial.unlink(missing_ok=True)
            verify_hash(target, digest)
        source = directory / "all.parquet"
        target = root / "db" / f"{table}.duckdb"
        with duckdb.connect(str(target.resolve()), config={"threads": "1"}) as db:
            db.execute("CREATE OR REPLACE TABLE data_table AS SELECT * FROM read_parquet(?)", [str(source)])
            rows = db.execute("SELECT count(*) FROM data_table").fetchone()[0]
        if rows != parquet.read_metadata(source).num_rows or rows != reference["rows"]:
            raise ValueError(f"Row count mismatch in {table}")
    selected_cases(root, split)
    (root / "manifest.json").write_text(json.dumps(pinned, indent=2) + "\n", encoding="utf-8")


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
    parser.add_argument("--split", choices=SUBSET_FILES, default="test")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--fetch", action="store_true")
    options = parser.parse_args()
    prepare(options.root or SUBSET_ROOTS[options.split], options.fetch, options.split)
