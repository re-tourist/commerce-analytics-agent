import argparse
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path

from commercelens.application.agent.graph import VARIANTS
from commercelens.application.contracts import Investigation, ToolError
from commercelens.bootstrap import olist_agent, olist_data
from commercelens.infrastructure.analytics.investigation import investigate
from commercelens.domain.metrics import METRICS


def main() -> None:
    parser = argparse.ArgumentParser(description="CommerceLens commerce analytics")
    parser.add_argument("--db", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    ask = commands.add_parser("ask", help="Ask the configured model to plan an analysis")
    ask.add_argument("question")
    ask.add_argument("--variant", choices=VARIANTS, default="full")
    metric = commands.add_parser("metric", help="Run the deterministic metric tool directly")
    metric.add_argument("metric", choices=METRICS)
    metric.add_argument("--group")
    metric.add_argument("--limit", type=int, default=10)
    for option in ("start", "end", "baseline-start", "baseline-end"):
        metric.add_argument(f"--{option}", type=date.fromisoformat)
    args = vars(parser.parse_args())
    db, command = args.pop("db"), args.pop("command")
    try:
        if command == "ask":
            answer = olist_agent(args["variant"], db).run(args["question"])
            result = asdict(answer)
        else:
            result = asdict(investigate(olist_data(db), Investigation(**args)))
    except ToolError as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    if command == "ask" and answer.status == "error":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
