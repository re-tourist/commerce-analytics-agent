"""Bounded single-agent workflow. The model proposes tools, and the graph authorizes them."""

from dataclasses import dataclass, replace
from decimal import Decimal
from time import perf_counter
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from commercelens.application.contracts import (
    Answer, Citation, DataTool, Evidence, Investigation, Plan, Planner, SchemaBindingError, ToolError,
)
from commercelens.domain.calendar import calendar_cohorts, repair_month_end
from commercelens.domain.metrics import METRICS, RELATIONS


@dataclass(frozen=True)
class Features:
    retrieval: bool = False
    investigation: bool = False
    verification: bool = False


VARIANTS = {
    "sql": Features(),
    "sql_rag": Features(retrieval=True),
    "sql_rag_skills": Features(retrieval=True, investigation=True),
    "full": Features(retrieval=True, investigation=True, verification=True),
}

SCHEMA_REPAIR_HINTS = {
    "relation": "Use the exact relation name shown in the schema, without a schema or catalog prefix. "
                "The subject of the question does not name a table.",
    "bind": "Check that every column is copied exactly from the schema and quoted with double quotes. "
            "Check the column's source alias, grouping and function input types.",
}

SEMANTIC_GUIDANCE = (
    "\nBefore writing SQL, identify the requested measure, eligible rows, grouping grain and answer type. "
    "Use a SQL boolean for a yes-or-no question: evaluate existence or the requested comparison. "
    "When a threshold describes an aggregate, calculate that aggregate over the eligible rows before comparing. "
    "Rank using the requested measure at the requested grain. In the final SELECT project only the requested "
    "answer, excluding helper columns used to rank or calculate it. Preserve duplicate list values unless the "
    "question asks for distinct values. Compare and sort values using the requested units and data type."
)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class State(TypedDict, total=False):
    question: str
    context: str
    citations: list[Citation]
    trace: list[dict]
    plan: Plan
    evidence: Evidence
    attempts: int
    model_usage: list[dict]
    failure: str
    feedback: str
    repair_hint: str
    answer: Answer


class Agent:
    def __init__(
        self, data: DataTool, planner: Planner, features: Features,
        retrieve: Callable[[str], list[Citation]] | None = None,
        analyze: Callable[[DataTool, Investigation], Evidence] | None = None,
        olist: bool = True,
        schema_grounding: bool = False,
        targeted_retry: bool | None = None,
        semantic_guidance: bool = False,
    ):
        self.data = data
        self.planner = planner
        self.features = features
        self.retrieve = retrieve if features.retrieval and olist else None
        self.analyze = analyze if features.investigation and olist else None
        self.olist = olist
        self.schema_grounding = schema_grounding
        self.targeted_retry = schema_grounding if targeted_retry is None else targeted_retry
        self.semantic_guidance = semantic_guidance
        graph = StateGraph(State)
        for node in ("context", "plan", "execute", "verify", "render"):
            graph.add_node(node, getattr(self, f"_{node}"))
        graph.add_edge(START, "context")
        graph.add_edge("context", "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "verify")
        graph.add_conditional_edges("verify", self._next, {"plan": "plan", "render": "render"})
        graph.add_edge("render", END)
        self.graph = graph.compile()

    def run(self, question: str) -> Answer:
        return self.graph.invoke({
            "question": question.strip(), "trace": [], "model_usage": [], "attempts": 0,
        })["answer"]

    def _context(self, state: State) -> dict:
        started = perf_counter()
        schema = self.data.schema()
        if self.schema_grounding:
            context = "Available SQL schema (copy the identifiers exactly):\n" + "\n".join(
                f"CREATE TABLE {quote_identifier(name)} (\n  "
                + ",\n  ".join(f"{quote_identifier(col)} {dtype}" for col, dtype in columns)
                + "\n)"
                for name, columns in schema.items()
            )
            context += (
                "\nUse the quoted table name above in FROM. Qualify column references with its alias if needed. "
                "Only use columns listed for that table, including punctuation and spaces as shown."
            )
        else:
            context = "\n".join(f"{name}({', '.join(f'{col} {dtype}' for col, dtype in columns)})"
                                for name, columns in schema.items())
        if self.olist:
            context += "\nHistorical Olist sample. Grouping/dates are by purchase_date.\n" + "\n".join(
                f"{name}: {RELATIONS[name]}" for name in schema if name in RELATIONS
            )
        citations = self.retrieve(state["question"]) if self.retrieve else []
        return {"context": context, "citations": citations, "trace": [{
            "step": "context", "relations": list(schema), "retrieved": [doc.id for doc in citations],
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        }]}

    def _plan(self, state: State) -> dict:
        started = perf_counter()
        prompt = (
            'Translate the question into one JSON tool plan. '
            'For a data answer emit {"tool":"sql","sql":"SELECT ..."} in DuckDB. '
            'Return only requested columns and rows, ordered if ranking is requested. Use explicit column aliases. '
            'For an unanswerable question emit {"tool":"unsupported","reason":"short explanation"}. '
            'Use only the visible columns and relations. Use double quotes for identifiers with spaces. '
            'Avoid SQL comments, external relations, pragmas and writes. Use casts for explicit dates.\n'
            + state["context"]
        )
        if self.olist:
            prompt += (
                "\nFor Olist: payment_value is already aggregated at order grain. "
                "For seller/category monetary questions use item price. BRL is the currency, never a state filter. "
                "For late rate use AVG(CAST(is_late AS INT)) to exclude NULL. "
                "For review-score comparisons between on-time and late orders, filter is_late IS NOT NULL "
                "and review_score IS NOT NULL, then GROUP BY is_late. "
                "For distinct seller counts by customer state use items.customer_state. "
                "For delivered orders filter order_status = 'delivered'. "
                "Causal questions and unavailable fields (profit, refunds, inventory, carrier) are unsupported."
            )
        else:
            prompt += "\nUse a single row and column for scalar answers and a single column for lists."
        if self.semantic_guidance:
            prompt += SEMANTIC_GUIDANCE
        if self.retrieve:
            prompt += '\nFor business definitions emit {"tool":"knowledge"}. Reference context follows.'
            for citation in state["citations"]:
                prompt += f"\n[{citation.id}] {citation.excerpt}"
        if self.analyze:
            prompt += (
                '\nFor a metric investigation (cohort comparison or group ranking), prefer '
                '{"tool":"investigate","investigation":{"metric":"…","group":"…","start":"YYYY-MM-DD",'
                '"end":"YYYY-MM-DD","baseline_start":"YYYY-MM-DD","baseline_end":"YYYY-MM-DD","limit":10}}. '
                "End dates are exclusive. For a whole month, use its first day as start and the first day of "
                "the next month as end. Omit unrequested filters and group limits. "
                "Use SQL for other questions and specific population conditions. Copy the metric key and group "
                "name exactly. For category merchandise value use metric merchandise_value and group category. "
                "For comparing on-time and late reviews, use review_score grouped by is_late without a "
                "date window unless the question specifies dates. "
                "Available metric keys and groups: "
                + "; ".join(f"{key} [{', '.join(metric.dimensions)}]" for key, metric in METRICS.items())
            )
        if self.olist:
            months = sorted(calendar_cohorts(state["question"]))
            if months:
                prompt += "\nExplicit purchase months: " + ", ".join(str(month)[:7] for month in months) + "."
        if state.get("feedback"):
            prompt += f"\nPrevious attempt failed verification: {state['feedback']}. Return a corrected plan."
            if state.get("repair_hint"):
                prompt += f" {state['repair_hint']}"
        failure = ""
        usage = list(state["model_usage"])
        try:
            call = self.planner.plan(prompt, state["question"])
            plan = call.plan
            usage.append({
                "model": self.planner.name, "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens, "cost_usd": call.cost_usd,
            })
            if plan.reason == "invalid_model_plan":
                failure = "Invalid model plan"
        except ToolError as exc:
            failure = str(exc)
            plan = Plan("unsupported")
        return {
            "plan": plan, "attempts": state["attempts"] + 1, "failure": failure, "model_usage": usage,
            "trace": [*state["trace"], {
                "step": "plan", "tool": plan.tool,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            }],
        }

    def _execute(self, state: State) -> dict:
        started = perf_counter()
        plan = state["plan"]
        evidence = Evidence(citations=list(state["citations"]))
        failure = state["failure"]
        repair_hint = ""
        try:
            if failure:
                pass
            elif plan.tool == "sql" and plan.sql:
                evidence.sql = plan.sql
                evidence.result = self.data.query(plan.sql)
            elif plan.tool == "investigate" and self.analyze and plan.investigation:
                spec = plan.investigation
                months = calendar_cohorts(state["question"])
                adjusted = replace(
                    spec, end=repair_month_end(spec.start, spec.end, months),
                    baseline_end=repair_month_end(spec.baseline_start, spec.baseline_end, months),
                )
                evidence = self.analyze(self.data, adjusted)
                evidence.citations = list(state["citations"])
                if spec != adjusted:
                    evidence.calculations["calendar_month_end_adjusted"] = True
            elif plan.tool == "knowledge" and state["citations"]:
                pass
            elif plan.tool != "unsupported":
                raise ToolError("Selected tool is unavailable or missing parameters")
        except ToolError as exc:
            failure = str(exc)
            if self.targeted_retry and isinstance(exc, SchemaBindingError):
                repair_hint = SCHEMA_REPAIR_HINTS[exc.phase]
        return {"evidence": evidence, "failure": failure, "repair_hint": repair_hint, "trace": [*state["trace"], {
            "step": "execute", "tool": plan.tool, "outcome": "error" if failure else "ok",
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        }]}

    def _verify(self, state: State) -> dict:
        if not self.features.verification:
            return {}
        evidence = state["evidence"]
        failure = state["failure"]
        if not failure and evidence.result and evidence.result.truncated:
            failure = "Result exceeded the output budget. Aggregate or add an explicit limit."
        if not failure and evidence.calculations:
            calc = evidence.calculations
            if calc["group_by"] and calc["delta"] is not None:
                total = sum((item["delta_contribution"] for item in calc["groups"]), Decimal(0))
                total += calc["omitted_delta_contribution"]
                if abs(total - calc["delta"]) > Decimal("1e-12"):
                    failure = "Group contributions do not reconcile with the overall change"
        return {"failure": failure, "feedback": failure, "trace": [*state["trace"], {
            "step": "verify", "outcome": "failed" if failure else "passed",
        }]}

    def _next(self, state: State) -> str:
        if (self.features.verification and state["failure"] and state["attempts"] < 2
                and not state["failure"].startswith("Model request failed")):
            return "plan"
        return "render"

    def _render(self, state: State) -> dict:
        plan, evidence, failure = state["plan"], state["evidence"], state["failure"]
        status = "ok"
        unconfirmed = []
        limits = ["Results describe the sampled orders and the requested cohort."] if self.olist else []
        if failure:
            status, summary = "error", failure
        elif plan.tool == "unsupported":
            status, summary = "unsupported", "The available data or tools cannot answer this question."
            unconfirmed.append(state["question"])
        elif plan.tool == "knowledge":
            summary = "See the retrieved business definitions in the cited excerpts."
        elif evidence.calculations:
            result = evidence.calculations
            metric = METRICS[result["metric"]]
            current = result["current"]
            status = "empty" if current is None else "ok"
            summary = (f"{metric.name}: no eligible rows." if current is None
                       else f"{metric.name}: {current:.4f} {metric.unit}.")
            if result["delta"] is not None:
                summary += f" Change from baseline: {result['delta']:+.4f} {metric.unit}."
            if result["group_by"] == "seller_id" or result["metric"] == "review_score":
                unconfirmed.append("Whether the observed group differences were caused by the measured factors.")
        elif evidence.result is not None:
            count = len(evidence.result.rows)
            status = "empty" if not count else "ok"
            summary = f"Returned {count} result row{'s' if count != 1 else ''}."
            if evidence.result.truncated:
                limits.append("The displayed result exceeded its output budget.")
        else:
            status, summary = "error", "No evidence was produced"
        trace = [*state["trace"], {"step": "render", "outcome": status}]
        return {"answer": Answer(
            status, plan.tool, summary, evidence, limits, trace, state["model_usage"], failure or None,
            model_explanation=plan.reason[:400] if status == "unsupported" and plan.reason else None,
            unconfirmed=unconfirmed,
        )}
