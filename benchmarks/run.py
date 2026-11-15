"""Execute actual model runs and compare to independent Olist or official DataBench references."""

import argparse
from collections import Counter
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import json
from math import ceil
from pathlib import Path
from time import perf_counter

import duckdb

from benchmarks.olist_cases import cases
from commercelens.application.agent.graph import Agent, VARIANTS
from commercelens.bootstrap import model_from_env, olist_agent, olist_data
from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        converted = Decimal(str(value))
        return converted if converted.is_finite() else None
    except InvalidOperation:
        return None


def same_value(actual, expected):
    if isinstance(expected, bool):
        return str(actual).lower() == str(expected).lower()
    number = numeric(expected)
    if number is not None and numeric(actual) is not None:
        return abs(numeric(actual) - number) <= max(Decimal("0.000001"), abs(number) * Decimal("0.000001"))
    return actual == expected


def same_rows(actual, expected, ordered):
    if len(actual) != len(expected):
        return False
    if not ordered:
        actual = sorted(actual, key=lambda row: tuple(map(str, row)))
        expected = sorted(expected, key=lambda row: tuple(map(str, row)))
    return all(len(left) == len(right) and all(map(same_value, left, right))
               for left, right in zip(actual, expected, strict=True))


def score_olist(case, answer, expected):
    evidence = answer.evidence
    cited = {citation.id for citation in evidence.citations}
    result = {
        "retrieval_hit": bool(cited & set(case.citations)) if case.citations else None,
        "citation_precision": len(cited & set(case.citations)) / len(cited) if case.citations and cited else None,
        "numerical_correct": None, "sql_correct": None, "sql_executed": None,
        "tool_correct": False, "success": False,
    }
    if case.family == "unsupported":
        result["tool_correct"] = answer.tool == "unsupported"
        result["success"] = answer.status == "unsupported"
    elif case.family == "knowledge":
        result["tool_correct"] = answer.tool == "knowledge"
        result["success"] = (answer.status == "ok" and result["tool_correct"] and result["retrieval_hit"])
    else:
        result["tool_correct"] = answer.tool == "sql" or bool(case.metric and answer.tool == "investigate")
        calc = evidence.calculations
        actual = evidence.result.rows if evidence.result is not None else []
        if calc:
            if calc.get("metric") != case.metric:
                actual = []
            elif case.family == "contribution":
                actual = [[row["group"], row["delta_contribution"]] for row in calc["groups"]]
            else:
                actual = [[calc["current"]]]
        correct = (answer.status in {"ok", "empty"} and evidence.result is not None
                   and not evidence.result.truncated and same_rows(actual, expected, case.ordered))
        if answer.tool == "sql":
            result["sql_executed"] = evidence.result is not None
            result["sql_correct"] = correct
        if any(any(numeric(value) is not None for value in row) for row in expected):
            result["numerical_correct"] = correct
        result["success"] = correct and result["tool_correct"]
    return result


def collect(case_id, variant, agent, question, grader):
    started = perf_counter()
    answer = agent.run(question)
    elapsed = round((perf_counter() - started) * 1000, 2)
    grades = grader(answer)
    failure = None
    if not grades["success"]:
        if answer.status == "error":
            failure = "model_error" if "model" in (answer.failure or "").lower() else "tool_error"
        elif not grades["tool_correct"] or answer.status == "unsupported":
            failure = "routing"
        elif grades["retrieval_hit"] is False:
            failure = "retrieval"
        else:
            failure = "answer_mismatch"
    return {
        "id": case_id, "variant": variant, "model": agent.planner.name, "elapsed_ms": elapsed,
        "failure_type": failure, "answer": asdict(answer), **grades,
    }


def summarize(records):
    def mean(rows, key):
        values = [row[key] for row in rows if row[key] is not None]
        return sum(values) / len(values) if values else None

    summary = {}
    for variant in sorted({row["variant"] for row in records}):
        rows = [row for row in records if row["variant"] == variant]
        times = sorted(row["elapsed_ms"] for row in rows)
        calls = [usage for row in rows for usage in row["answer"]["model_usage"]]
        summary[variant] = {
            "tasks": len(rows),
            "metrics": {
                key: mean(rows, key) for key in ("success", "sql_correct", "sql_executed", "numerical_correct",
                                                "tool_correct", "retrieval_hit", "citation_precision")
            },
            "sql_attempts": sum(row["sql_executed"] is not None for row in rows),
            "eligible_numerical_tasks": sum(row["numerical_correct"] is not None for row in rows),
            "p50_ms": times[ceil(len(times) * 0.50) - 1],
            "p95_ms": times[ceil(len(times) * 0.95) - 1],
            "failure_counts": dict(Counter(row["failure_type"] for row in rows if row["failure_type"])),
            "model_calls_reporting_usage": len(calls),
            "input_tokens": sum(call["input_tokens"] for call in calls),
            "output_tokens": sum(call["output_tokens"] for call in calls),
            "metered_api_cost_usd": (sum(call["cost_usd"] for call in calls)
                                     if calls and all(call["cost_usd"] is not None for call in calls) else None),
        }
    return summary


def run_olist(variant, limit, *, agent=None):
    agent = agent if agent is not None else olist_agent(variant)
    with duckdb.connect(str(olist_data().path), read_only=True, config={"enable_external_access": "false"}) as db:
        references = {case.id: db.execute(case.sql).fetchall() for case in cases() if case.sql}
    for case in cases()[:limit]:
        yield collect(case.id, variant, agent, case.question,
                      lambda answer: score_olist(case, answer, references.get(case.id)))


EXPERIMENTS = {
    "full_ddl_only": (True, False, False),
    "full_retry_only": (False, True, False),
    "full_schema_grounded": (True, True, False),
    "full_semantic": (True, True, True),
}


def run_databench(variant, limit, split="test"):
    from benchmarks.databench import SUBSET_ROOTS, selected_cases, score

    root = SUBSET_ROOTS[split]
    planned = selected_cases(root, split)
    ddl, retry, semantics = EXPERIMENTS.get(variant, (False, False, False))
    features = VARIANTS["full" if variant in EXPERIMENTS else variant]
    for table, cases_for_table in planned.items():
        data = ReadOnlyDuckDB(root / "db" / f"{table}.duckdb", ("data_table",))
        agent = Agent(data, model_from_env(), features, olist=False, schema_grounding=ddl,
                      targeted_retry=retry, semantic_guidance=semantics)
        for case in cases_for_table:
            if limit is not None and limit <= 0:
                return
            yield collect(case["id"], variant, agent, case["question"], lambda answer: score(answer, case))
            if limit is not None:
                limit -= 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("track", choices=("olist", "databench"))
    parser.add_argument("--variant", choices=(*VARIANTS, *EXPERIMENTS), action="append")
    parser.add_argument("--split", choices=("test", "dev", "holdout"))
    parser.add_argument("--compare-schema-grounding", action="store_true",
                        help="Run the DataBench full baseline and schema-grounded full candidate")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.track != "databench" and (args.split or args.compare_schema_grounding):
        parser.error("split and schema-grounding comparison require DataBench")
    if args.track == "olist" and any(variant in EXPERIMENTS for variant in (args.variant or ())):
        parser.error("experimental variants require DataBench")
    if args.variant and len(args.variant) != len(set(args.variant)):
        parser.error("each variant can be specified only once")
    if args.compare_schema_grounding and args.variant:
        parser.error("schema-grounding comparison selects both variants itself")
    split = args.split or "test"
    if args.track == "olist":
        variants = args.variant or tuple(VARIANTS)
    elif args.compare_schema_grounding:
        variants = ("full", "full_schema_grounded")
    else:
        variants = args.variant or ("full",)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    with (args.output / "records.jsonl").open("w", encoding="utf-8") as stream:
        for variant in variants:
            run = run_olist(variant, args.limit) if args.track == "olist" else run_databench(variant, args.limit, split)
            for record in run:
                records.append(record)
                stream.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
                stream.flush()
                print(f"{variant} {record['id']} {'pass' if record['success'] else record['failure_type']}", flush=True)
    summary = {"track": args.track, "limit": args.limit, "variants": summarize(records)}
    if args.track == "databench":
        summary["split"] = split
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
