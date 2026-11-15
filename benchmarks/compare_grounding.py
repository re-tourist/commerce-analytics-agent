"""Compare paired DataBench attempts without publishing data or questions."""

import argparse
from collections import Counter
import json
from pathlib import Path


VARIANTS = ("full", "full_schema_grounded")


def outcome(row):
    if row["success"]:
        return "pass"
    if row["failure_type"] != "tool_error":
        return row["failure_type"]
    message = row["answer"]["failure"]
    if message == "Query must read only from the allowed analytical relations":
        return "relation_policy"
    if message == "Query failed (BinderException)":
        return "binding"
    if message == "Could not parse or validate SQL":
        return "sql_parse"
    return "other_tool_error"


def compare(records):
    groups = {variant: {} for variant in VARIANTS}
    for record in records:
        variant, identifier = record["variant"], record["id"]
        if variant not in groups or identifier in groups[variant]:
            raise ValueError("Expected one record per task and comparison variant")
        groups[variant][identifier] = record
    baseline, grounded = (groups[variant] for variant in VARIANTS)
    if not baseline or baseline.keys() != grounded.keys():
        raise ValueError("The comparison requires matching nonempty task IDs")
    if len({row["model"] for row in records}) != 1:
        raise ValueError("The comparison requires identical model names")
    transitions = Counter()
    per_table = {}
    for identifier in sorted(baseline):
        old, new = baseline[identifier], grounded[identifier]
        transitions[f"{outcome(old)} -> {outcome(new)}"] += 1
        table = identifier.split(":", 1)[0]
        row = per_table.setdefault(table, Counter())
        row.update(tasks=1, baseline_pass=int(old["success"]), grounded_pass=int(new["success"]),
                   baseline_executed=int(old["sql_executed"]), grounded_executed=int(new["sql_executed"]))
    return {
        "tasks": len(baseline),
        "model": next(iter(baseline.values()))["model"],
        "outcomes": {variant: dict(sorted(Counter(map(outcome, group.values())).items()))
                     for variant, group in groups.items()},
        "transitions": dict(sorted(transitions.items())),
        "per_table": per_table,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.records.read_text(encoding="utf-8").splitlines()]
    args.output.write_text(json.dumps(compare(records), indent=2) + "\n", encoding="utf-8")
