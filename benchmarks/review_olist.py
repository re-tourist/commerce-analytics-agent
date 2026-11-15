"""Generate the local reference packet for a human Olist benchmark review."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import duckdb

from benchmarks.olist_cases import cases
from commercelens.infrastructure.retrieval.knowledge import DOCUMENTS


SAMPLE_DIGEST = "93e5d327a4b40f9017d09c0e1648f0142fbc499fac7e2217816d2edde7dce175"
ABSTENTION_CHECKS = {
    "O037": "Check that cost of goods sold and net revenue are unavailable. Recorded payments and item prices cannot establish profit margin.",
    "O038": "Check that warehouse inventory and shortage events are unavailable. The seller and shipping fields cannot establish a warehouse shortage.",
    "O039": "Check that the carrier and a control or other causal comparison are unavailable. The observations can support a descriptive late rate in SP.",
    "O040": "Check that refund transactions, amounts and reasons are unavailable. Payment records cannot establish refunds by reason.",
}


def render(database: Path, audit: dict | None = None) -> str:
    docs = {document.id: document for document in DOCUMENTS}
    findings = {row["id"]: row for row in audit["cases"]} if audit else {}
    if audit and (audit["sample_sha256"] != SAMPLE_DIGEST or set(findings) != {case.id for case in cases()}):
        raise ValueError("Audit does not match the pinned sample or current case IDs")
    with duckdb.connect(str(database.resolve()), read_only=True, config={"enable_external_access": "false"}) as db:
        order_ids = db.execute("SELECT order_id FROM source.orders ORDER BY order_id").fetchall()
        digest = hashlib.sha256("\n".join(row[0] for row in order_ids).encode()).hexdigest()
        if digest != SAMPLE_DIGEST:
            raise ValueError("Database does not contain the pinned Olist benchmark sample")
        schema = db.execute("""
            SELECT table_name, list(column_name ORDER BY ordinal_position)
            FROM information_schema.columns WHERE table_schema = 'source'
            GROUP BY table_name ORDER BY table_name
        """).fetchall()
        lines = [
            "# Olist reference review packet",
            "",
            f"Sample order ID SHA-256: `{digest}`",
            "",
            "Reviewer: ____________________",
            "",
            "Review date: __________________",
            "",
            "Mark each case after checking the question against the reference. Record the case ID and "
            "proposed correction for discrepancies. For unavailable data, verify the rubric against the source "
            "schema. For knowledge questions, check that the excerpt answers the question.",
            "",
            "## Source columns",
            "",
        ]
        for table, columns in schema:
            lines.append(f"- `source.{table}`: {', '.join(columns)}")
        groups = Counter()
        for case in cases():
            lines.extend(["", f"## {case.id} · {case.family}", "", case.question, ""])
            if case.id in findings:
                result = findings[case.id]
                lines.extend([f"**{result['status']}** · {result['evidence']}", ""])
                if result["review"]:
                    lines.extend([f"Reviewer decision · {result['review']}", ""])
            if case.sql:
                rows = db.execute(case.sql).fetchall()
                groups["SQL references"] += 1
                lines.extend([
                    "```sql", case.sql, "```", "",
                    "Expected rows", "", "```json",
                    json.dumps(rows, default=str, indent=2, ensure_ascii=False), "```",
                ])
            elif case.family == "unsupported":
                groups["abstention rubrics"] += 1
                lines.append(ABSTENTION_CHECKS[case.id])
            else:
                groups["knowledge references"] += 1
                lines.extend(f"> {docs[identifier].title} · {docs[identifier].excerpt}" for identifier in case.citations)
            lines.extend(["", "- [ ] Reviewed", "", "Findings: ____________________"])
    lines.extend(["", "## Coverage", ""])
    lines.extend(f"- {total} {kind}" for kind, total in groups.items())
    return "\n".join([*lines, ""])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/olist.duckdb"))
    parser.add_argument("--output", type=Path, default=Path("data/olist-reference-review.md"))
    parser.add_argument("--audit", type=Path, default=Path("reports/olist-reference-audit.json"))
    arguments = parser.parse_args()
    packet = render(arguments.db, json.loads(arguments.audit.read_text(encoding="utf-8")) if arguments.audit.is_file() else None)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(packet, encoding="utf-8")
