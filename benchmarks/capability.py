"""Paired local-model diagnostics using the unchanged DataBench scorer."""

import argparse
from collections import Counter
import json
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.databench import SUBSET_ROOTS, score, selected_cases
from benchmarks.run import collect, numeric, summarize
from benchmarks.typed_analysis import AnalysisPlan, PROMPT, compile_sql
from commercelens.application.agent.graph import Agent, VARIANTS
from commercelens.application.contracts import Plan
from commercelens.bootstrap import model_from_env
from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB
from commercelens.infrastructure.llm.openai_compatible import OpenAICompatible


ARMS = {
    "full": (False, 384, False),
    "grounded": (True, 384, False),
    "grounded_768": (True, 768, False),
    "typed": (True, 384, True),
}


class DiagnosticPlanner(OpenAICompatible):
    def __init__(self, endpoint, model, cap, schema=None):
        super().__init__(endpoint, model, local=True)
        self.cap = cap
        self.schema = schema
        self.attempts = []
        if schema:
            self.relation, self.columns = next(iter(schema.items()))
            self.column_names = {name for name, _ in self.columns}
            self.analysis_prompt = PROMPT + "\nAvailable schema:\n" + json.dumps(schema, ensure_ascii=False)

    def _complete(self, prompt, question, *, max_tokens=384):
        if self.schema:
            _, separator, feedback = prompt.rpartition("\nPrevious attempt failed verification: ")
            prompt = self.analysis_prompt
            if separator:
                prompt += separator + feedback
        self.attempts.append({"finish_reason": None})
        payload = super()._complete(prompt, question, max_tokens=self.cap)
        choices = payload.get("choices") or [{}]
        self.attempts[-1]["finish_reason"] = choices[0].get("finish_reason")
        return payload

    def _decode_plan(self, content):
        if not self.schema:
            return super()._decode_plan(content)
        self.attempts[-1]["analysis_json"] = content
        try:
            analysis = AnalysisPlan.model_validate_json(content)
            if analysis.kind == "unsupported":
                return Plan("unsupported", reason="Analysis grammar does not cover the request")
            return Plan("sql", sql=compile_sql(analysis, self.relation, self.column_names))
        except ValueError as exc:
            self.attempts[-1]["analysis_error"] = str(exc)
            raise


def result_contract(table, semantic):
    if table is None:
        return None
    rows = table["rows"]
    is_list = semantic.startswith("list[")
    if len(table["columns"]) != 1 or (not is_list and len(rows) != 1):
        return "result_shape"
    values = [row[0] for row in rows]
    # The production evaluator accepts a serialized list in one cell.
    if is_list and len(values) == 1 and isinstance(values[0], str) and values[0].startswith("["):
        return None
    if semantic == "boolean" and any(not isinstance(value, bool) for value in values):
        return "result_type"
    if "number" in semantic and any(numeric(value) is None for value in values):
        return "result_type"
    return None


def classify(record, semantic):
    if record["success"]:
        return "pass"
    answer = record["answer"]
    failure = answer["failure"] or ""
    if failure.startswith("Model request failed"):
        return "transport"
    if failure == "Invalid model plan":
        last = record["attempts"][-1]
        if last["finish_reason"] == "length":
            return "token_limit"
        return "analysis_plan_rejected" if "analysis_error" in last else "malformed_model_plan"
    if "Could not parse" in failure or "ParserException" in failure:
        return "sql_parse_or_validation"
    if "allowed analytical relations" in failure:
        return "relation_binding"
    if "BinderException" in failure:
        return "schema_or_type_binding"
    if "output budget" in failure:
        return "output_budget"
    if failure:
        return "other_execution_or_policy"
    if answer["status"] == "unsupported":
        return "unsupported"
    return result_contract(answer["evidence"]["result"], semantic) or "value_mismatch"


def counts(records):
    return {
        "tasks": len(records),
        "correct": sum(row["success"] for row in records),
        "sql_completed": sum(row["sql_executed"] for row in records),
        "failures": dict(Counter(row["diagnosis"] for row in records if not row["success"])),
        "finish_reasons": dict(Counter(
            attempt["finish_reason"] for row in records for attempt in row["attempts"]
        )),
        "completion_tokens_max": max(
            (call["output_tokens"] for row in records for call in row["answer"]["model_usage"]),
            default=0,
        ),
    }


def paired(left, right):
    old = {row["id"]: row["success"] for row in left}
    new = {row["id"]: row["success"] for row in right}
    if old.keys() != new.keys():
        raise ValueError("Paired comparison requires matching task IDs")
    return {
        "fixed": sum(not old[key] and new[key] for key in old),
        "regressed": sum(old[key] and not new[key] for key in old),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=("dev", "regression"), required=True)
    parser.add_argument("--arm", choices=ARMS, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.arm) != len(set(args.arm)) or ("typed" in args.arm and args.cohort != "dev"):
        parser.error("Select distinct arms and use typed only on the development cohort")
    configured = model_from_env()
    endpoint = configured.url.removesuffix("/chat/completions")
    if urlsplit(endpoint).hostname not in {"127.0.0.1", "::1", "localhost"} or configured.headers:
        parser.error("Use an unauthenticated loopback model server for this experiment")
    split = "dev" if args.cohort == "dev" else "holdout"  # Legacy manifest and directory names.
    root = SUBSET_ROOTS[split]
    tables = selected_cases(root, split)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    with (args.output / "records.jsonl").open("x", encoding="utf-8") as stream:
        for table, cases in tables.items():
            data = ReadOnlyDuckDB(root / "db" / f"{table}.duckdb", ("data_table",))
            agents = {}
            for arm in args.arm:
                grounded, cap, typed = ARMS[arm]
                planner = DiagnosticPlanner(endpoint, configured.name, cap, data.schema() if typed else None)
                agents[arm] = Agent(data, planner, VARIANTS["full"], olist=False, schema_grounding=grounded)
            for index, case in enumerate(cases):
                # Rotate the first arm to distribute ordering and cache effects.
                offset = index % len(args.arm)
                for arm in args.arm[offset:] + args.arm[:offset]:
                    agent = agents[arm]
                    agent.planner.attempts = []
                    record = collect(case["id"], arm, agent, case["question"], lambda answer: score(answer, case))
                    record["attempts"] = agent.planner.attempts
                    record["answer_type"] = case["type"]
                    record["diagnosis"] = classify(record, case["type"])
                    records.append(record)
                    stream.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
                    stream.flush()
                    print(arm, case["id"], record["diagnosis"], flush=True)
    groups = {arm: [row for row in records if row["variant"] == arm] for arm in args.arm}
    summary = {
        "cohort": args.cohort,
        "model": configured.name,
        "arms": {
            arm: {
                **counts(rows),
                **summarize(rows)[arm],
                "by_answer_type": {
                    kind: counts([row for row in rows if row["answer_type"] == kind])
                    for kind in sorted({row["answer_type"] for row in rows})
                },
                "vs_grounded": paired(groups["grounded"], rows) if "grounded" in groups else None,
            }
            for arm, rows in groups.items()
        },
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
