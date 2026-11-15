from collections import deque
from datetime import date

import duckdb
from fastapi.testclient import TestClient
import pytest

from commercelens.application.agent.graph import Agent, VARIANTS
from commercelens.application.contracts import Investigation, ModelCall, Plan
from commercelens.infrastructure.analytics.investigation import investigate
from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB
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


def test_abstention_separates_explanation_from_evidence(analytical_data):
    question = "How much did a carrier change affect late deliveries?"
    reason = "Carrier history is unavailable."
    agent = Agent(analytical_data, ScriptedPlanner(Plan("unsupported", reason=reason)), VARIANTS["full"])
    answer = agent.run(question)
    assert answer.status == "unsupported"
    assert answer.model_explanation == reason
    assert answer.unconfirmed == [question]
    assert answer.evidence.result is None
    assert reason not in answer.limits


@pytest.mark.parametrize(("first_sql", "hint"), [
    ("SELECT count(*) FROM undisclosed_relation", "The subject of the question does not name a table"),
    ('SELECT "Retail Price" FROM data_table', "Check that every column is copied exactly"),
])
def test_schema_grounding_retries_with_safe_hints(tmp_path, first_sql, hint):
    database = tmp_path / "table.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute('CREATE TABLE data_table AS SELECT 20 AS "Retail ""Price"""')
        connection.execute("CREATE TABLE undisclosed_relation AS SELECT 42 AS secret_value")
    data = ReadOnlyDuckDB(database, ("data_table",))
    corrected_sql = 'SELECT "Retail ""Price""" FROM "data_table"'
    planner = ScriptedPlanner(Plan("sql", first_sql), Plan("sql", corrected_sql))
    agent = Agent(data, planner, VARIANTS["full"], olist=False, schema_grounding=True)
    answer = agent.run("What is the retail price?")
    assert answer.evidence.result.rows == [[20]]
    assert 'CREATE TABLE "data_table"' in planner.prompts[0]
    assert '"Retail ""Price""" INTEGER' in planner.prompts[0]
    assert hint in planner.prompts[1]
    assert all("undisclosed_relation" not in prompt and "secret_value" not in prompt for prompt in planner.prompts)
    assert [step["outcome"] for step in answer.trace if step["step"] == "verify"] == ["failed", "passed"]


@pytest.mark.parametrize(("ddl", "retry"), [(True, False), (False, True)])
def test_ddl_and_retry_are_independent(analytical_data, ddl, retry):
    planner = ScriptedPlanner(Plan("sql", "SELECT * FROM unavailable"), Plan("sql", "SELECT count(*) FROM orders"))
    answer = Agent(analytical_data, planner, VARIANTS["full"], olist=False, schema_grounding=ddl,
                   targeted_retry=retry).run("Count orders")
    assert answer.evidence.result.rows == [[6]]
    assert ('CREATE TABLE "orders"' in planner.prompts[0]) == ddl
    assert ("The subject of the question does not name a table" in planner.prompts[1]) == retry


def test_semantic_guidance_uses_question_without_gold_metadata(analytical_data):
    question = "Are there any orders?"
    planner = ScriptedPlanner(Plan("sql", "SELECT count(*) > 0 FROM orders"))
    answer = Agent(analytical_data, planner, VARIANTS["full"], olist=False, semantic_guidance=True).run(question)
    assert answer.evidence.result.rows == [[True]]
    assert "Use a SQL boolean for a yes-or-no question" in planner.prompts[0]


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
