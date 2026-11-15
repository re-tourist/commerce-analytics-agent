"""Measure a narrow SQL cohort instruction using the unchanged Olist grader."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.run import run_olist, summarize
from commercelens.application.agent.graph import Agent, VARIANTS
from commercelens.bootstrap import model_from_env, olist_data
from commercelens.infrastructure.analytics.investigation import investigate
from commercelens.infrastructure.retrieval.knowledge import Knowledge


COHORT_GUIDANCE = (
    "\nFor SQL over a named whole purchase month, use purchase_date >= its first day AND "
    "purchase_date < the first day of the next month; BETWEEN includes its upper bound. "
    "Eligible delivery means is_late IS NOT NULL; delivered status alone can include unknown "
    "lateness. At order grain use AVG(CAST(is_late AS INT)) for a 0–1 fraction. "
    "For comparisons grouped by lateness, exclude NULL lateness before grouping."
)


class CohortAgent(Agent):
    def _context(self, state):
        result = super()._context(state)
        result["context"] += COHORT_GUIDANCE
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    planner = model_from_env()
    if urlsplit(planner.url).hostname not in {"127.0.0.1", "::1", "localhost"} or planner.headers:
        parser.error("Use an unauthenticated loopback model server")
    agent = CohortAgent(olist_data(), planner, VARIANTS["full"], Knowledge().search, investigate)
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    with (args.output / "records.jsonl").open("x", encoding="utf-8") as stream:
        for record in run_olist("full_cohort_grounding", None, agent=agent):
            records.append(record)
            stream.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
            stream.flush()
            print(record["id"], "pass" if record["success"] else record["failure_type"], flush=True)
    summary = {"track": "olist", "limit": None, "variants": summarize(records)}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
