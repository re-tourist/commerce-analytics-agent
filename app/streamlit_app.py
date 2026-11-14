"""Interactive UI. Each submission executes the real tools against the configured data."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
import json
from time import perf_counter

import streamlit as st

from commercelens.application.contracts import Answer, Investigation, ToolError
from commercelens.bootstrap import olist_agent, olist_data
from commercelens.domain.metrics import METRICS
from commercelens.infrastructure.analytics.investigation import investigate


SCENARIOS = {
    "Delivery performance": (
        "Compare late delivery rate by customer_state for July 2018 versus June 2018. "
        "Show the top 8 state contributions to the change.",
        Investigation("late_rate", "customer_state", date(2018, 7, 1), date(2018, 8, 1),
                      date(2018, 6, 1), date(2018, 7, 1), 8),
    ),
    "Merchandise performance": (
        "Compare merchandise value by category for July 2018 versus June 2018. "
        "Show the top 8 category contributions to the change.",
        Investigation("merchandise_value", "category", date(2018, 7, 1), date(2018, 8, 1),
                      date(2018, 6, 1), date(2018, 7, 1), 8),
    ),
    "Recorded payment value": (
        "Compare total recorded payment value in BRL for July 2018 versus June 2018. "
        "Show the top 8 customer_state contributions to the change.",
        Investigation("payment_value", "customer_state", date(2018, 7, 1), date(2018, 8, 1),
                      date(2018, 6, 1), date(2018, 7, 1), 8),
    ),
}


def value(number: Decimal | None, unit: str) -> str:
    if number is None:
        return "Unavailable"
    if unit == "share":
        return f"{number:.2%}"
    return f"{number:,.2f} {unit}"


st.set_page_config(page_title="CommerceLens", layout="wide")
st.title("CommerceLens")
st.caption("Commerce analytics over a stratified sample of 15,000 Olist orders")
scenario = st.radio("Scenario", tuple(SCENARIOS), horizontal=True)
example, specification = SCENARIOS[scenario]
mode = st.radio("Execution", ["Natural language", "Preconfigured metric"], horizontal=True)
if mode == "Natural language":
    question = st.text_area("Question", value=example, key=scenario, max_chars=2_000)
    run = st.button("Run analysis", type="primary", disabled=not question.strip())
else:
    st.write(METRICS[specification.metric].definition)
    st.caption("July 2018 compared with June 2018")
    run = st.button("Run metric", type="primary")

if run:
    with st.spinner("Running the analysis"):
        try:
            started = perf_counter()
            if mode == "Natural language":
                response = olist_agent().run(question)
                if response.status == "error":
                    st.error(response.summary)
                elif not response.evidence.calculations:
                    st.write(response.summary)
            else:
                evidence = investigate(olist_data(), specification)
                response = Answer(
                    "empty" if evidence.calculations["current"] is None else "ok",
                    "investigate", METRICS[specification.metric].name, evidence,
                    limits=["Results describe sampled Olist orders in the selected purchase cohorts."],
                    trace=[{"step": "investigate", "duration_ms": round((perf_counter() - started) * 1000, 2)}],
                )
            evidence = response.evidence
            if evidence.calculations:
                calc = evidence.calculations
                unit = calc["unit"]
                st.subheader("Calculated results")
                current, baseline, change = st.columns(3)
                current.metric("Current", value(calc["current"], unit))
                baseline.metric("Baseline", value(calc["baseline"], unit))
                delta = calc["delta"]
                change.metric("Change", f"{delta * 100:+.2f} pp" if unit == "share" and delta is not None
                              else value(delta, unit))
                st.caption(calc["definition"])
                inputs = []
                for label, window in calc["windows"].items():
                    if window is None:
                        continue
                    bounds = f"{window[0]} to {window[1]} (exclusive end)" if window[0] else "Entire sample"
                    inputs.append({
                        "Period": label.capitalize(), "Purchase window": bounds,
                        "Eligible rows": int(calc[f"{label}_population"]),
                        "Numerator or sum": str(calc[f"{label}_numerator"]),
                    })
                if calc["groups"]:
                    records = [
                        {key: float(val) if isinstance(val, Decimal) else val for key, val in row.items()}
                        for row in calc["groups"]
                    ]
                    if delta is not None:
                        chart_rows = records
                        contribution = "delta_contribution"
                        if unit == "share":
                            contribution = "Change contribution (pp)"
                            chart_rows = [{"group": row["group"], contribution: row["delta_contribution"] * 100}
                                          for row in records]
                        st.bar_chart(chart_rows, x="group", y=contribution, horizontal=True)
                    st.dataframe(records, hide_index=True)
                    if calc["omitted_groups"]:
                        st.caption(f"{calc['omitted_groups']} additional groups are included in the totals.")
                st.subheader("Query evidence")
                st.dataframe(inputs, hide_index=True)
            elif evidence.result:
                st.subheader("Query result")
                st.dataframe({name: [row[index] for row in evidence.result.rows]
                              for index, name in enumerate(evidence.result.columns)})
            if response.model_explanation:
                st.subheader("Model explanation")
                st.text(response.model_explanation)
            if evidence.assumptions:
                st.subheader("Business assumptions")
                for assumption in evidence.assumptions:
                    st.write(assumption)
            if response.unconfirmed:
                st.subheader("Unconfirmed")
                for conclusion in response.unconfirmed:
                    st.text(conclusion)
            for citation in evidence.citations:
                with st.expander(citation.title):
                    st.write(citation.excerpt)
            for limit in response.limits:
                st.caption(limit)
            if evidence.sql:
                with st.expander("Executed SQL" if evidence.result is not None else "Proposed SQL"):
                    st.code(evidence.sql, language="sql")
            with st.expander("Execution trace"):
                st.json(response.trace)
            st.download_button(
                "Download report",
                json.dumps({
                    "question": question if mode == "Natural language" else None,
                    "scenario": scenario, "execution": mode, **asdict(response),
                }, indent=2, default=str, ensure_ascii=False),
                "commercelens-report.json",
                "application/json",
                on_click="ignore",
            )
        except ToolError as exc:
            st.error(str(exc))
