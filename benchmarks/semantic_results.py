"""Publish aggregate and paired outcomes from recorded semantic experiment runs."""

import argparse
from collections import Counter
import json
from pathlib import Path

from benchmarks.compare_grounding import outcome
from benchmarks.databench import pinned_manifest
from benchmarks.run import summarize


def read_records(*directories):
    return [
        json.loads(line)
        for directory in directories
        for line in (directory / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def analyze(records, split, comparisons):
    manifest = pinned_manifest(split)
    expected = {case for table in manifest["tables"].values() for case in table["question_ids"]}
    groups = {}
    for row in records:
        group = groups.setdefault(row["variant"], {})
        if row["id"] in group:
            raise ValueError("Duplicate task in recorded variant")
        group[row["id"]] = row
    variants = {variant for pair in comparisons for variant in pair}
    if groups.keys() != variants or any(group.keys() != expected for group in groups.values()):
        raise ValueError(f"The {split} comparison does not match all pinned questions and arms")
    if len({row["model"] for row in records}) != 1:
        raise ValueError("All arms must record the same model alias")
    paired = {}
    for before, after in comparisons:
        left, right = groups[before], groups[after]
        changes = Counter(f"{outcome(left[case])} -> {outcome(right[case])}" for case in expected)
        paired[f"{before} vs {after}"] = {
            "gained": sum(not left[case]["success"] and right[case]["success"] for case in expected),
            "lost": sum(left[case]["success"] and not right[case]["success"] for case in expected),
            "transitions": dict(sorted(changes.items())),
        }
    return {
        "tasks_per_variant": len(expected),
        "variants": summarize(records),
        "outcomes": {variant: dict(sorted(Counter(map(outcome, group.values())).items()))
                     for variant, group in groups.items()},
        "paired": paired,
        "per_table_success": {
            table: {variant: sum(group[case]["success"] for case in ref["question_ids"])
                    for variant, group in groups.items()}
            for table, ref in manifest["tables"].items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("reports/runs"))
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    combined = "full_schema_grounded"
    semantic_pair = [(combined, "full_semantic")]
    dev = read_records(args.runs / "semantic-dev")
    exposed = read_records(args.runs / "schema-grounding-test", args.runs / "semantic-ablation")
    holdout = read_records(args.runs / "semantic-holdout")
    result = {
        "candidate_freeze": args.freeze,
        "archived_arms_commit": "69833ffc9ad7683d6b356bc7bc6dadb319a68307",
        "model": "Qwen2.5-Coder-3B-Instruct Q4_K_M",
        "gguf_sha256": "724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7",
        "data_revision": pinned_manifest("test")["revision"],
        "runtime": "llama.cpp b12383",
        "scorer": "databench-eval==4.0.1",
        "temperature": 0,
        "seed": 741,
        "max_output_tokens": 384,
        "max_model_attempts": 2,
        "sql_limits": {
            "timeout_seconds": 4, "duckdb_memory_limit": "128MB", "threads": 1,
            "max_output_rows": 200, "max_output_bytes": 100_000,
            "read_only": True, "external_access": False, "disk_spill": False,
        },
        "development": analyze(dev, "dev", semantic_pair),
        "exposed_factorial": analyze(exposed, "test", [
            ("full", "full_ddl_only"), ("full", "full_retry_only"),
            ("full_ddl_only", combined), ("full_retry_only", combined),
        ]),
        "independent_holdout": analyze(holdout, "holdout", [("full", combined), *semantic_pair]),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
