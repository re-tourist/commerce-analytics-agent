from collections import deque
from datetime import date

from fastapi.testclient import TestClient

from commercelens.application.agent.graph import Agent, VARIANTS
from commercelens.application.contracts import Investigation, ModelCall, Plan
from commercelens.infrastructure.analytics.investigation import investigate
from commercelens.infrastructure.retrieval.knowledge import Knowledge
from commercelens.interfaces import http


class ScriptedPlanner:
    name = "deterministic fixture"

    def __init__(self, *plans):
        self.plans = deque(plans)
        self.prompts = []

    def plan(self, prompt, question):
        self.prompts.append(prompt)
        return ModelCall(self.plans.popleft(), 8, 4, 0)


def test_verification_retries_without_bypassing_policy(analytical_data):
    planner = ScriptedPlanner(Plan("sql", "SELECT * FROM internal_notes"),
                              Plan("sql", "SELECT count(*) FROM orders"))
    agent = Agent(analytical_data, planner, VARIANTS["full"])
    answer = agent.run("Count orders")
    assert answer.status == "ok"
    assert answer.evidence.result.rows == [[6]]
    assert "Previous attempt failed verification" in planner.prompts[1]
    assert [step["outcome"] for step in answer.trace if step["step"] == "verify"] == ["failed", "passed"]
    assert len(answer.model_usage) == 2


def test_retrieval_returns_citations_and_sends_excerpts(analytical_data):
    planner = ScriptedPlanner(Plan("knowledge"))
    agent = Agent(analytical_data, planner, VARIANTS["sql_rag"], Knowledge().search)
    answer = agent.run("Define late delivery rate and eligible denominator")
    assert answer.status == "ok"
    assert "delivery-eligibility" in {citation.id for citation in answer.evidence.citations}
    assert "[delivery-eligibility]" in planner.prompts[0]


def test_http_uses_graph_and_metrics(monkeypatch, analytical_data):
    planner = ScriptedPlanner(Plan("sql", "SELECT count(*) FROM orders"))
    agent = Agent(analytical_data, planner, VARIANTS["sql"])
    monkeypatch.setattr(http, "olist_agent", lambda variant: agent)
    monkeypatch.setattr(http, "olist_data", lambda: analytical_data)
    client = TestClient(http.app)
    assert client.get("/health").status_code == 200
    assert client.post("/ask", json={"question": "Count orders"}).json()["evidence"]["result"]["rows"] == [[6]]
    assert client.post("/investigate", json={"metric": "order_count"}).json()["calculations"]["current"] == 6
    assert client.post("/investigate", json={"metric": "invalid"}).status_code == 422


def test_calendar_month_includes_last_day(analytical_data):
    spec = Investigation("order_count", start=date(2018, 7, 1), end=date(2018, 7, 31))
    agent = Agent(analytical_data, ScriptedPlanner(Plan("investigate", investigation=spec)), VARIANTS["full"],
                  analyze=investigate)
    answer = agent.run("Count orders in July 2018")
    assert answer.evidence.calculations["current"] == 3
    assert answer.evidence.calculations["calendar_month_end_adjusted"]


def test_explicit_exclusive_end_date_stays_unchanged(analytical_data):
    spec = Investigation("order_count", start=date(2018, 7, 1), end=date(2018, 7, 31))
    agent = Agent(analytical_data, ScriptedPlanner(Plan("investigate", investigation=spec)), VARIANTS["full"],
                  analyze=investigate)
    answer = agent.run("Count orders from 2018-07-01 up to but excluding 2018-07-31.")
    assert answer.evidence.calculations["current"] == 2
