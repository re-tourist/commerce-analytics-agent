"""Interactive UI. Each submission executes the real tools against the configured data."""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from time import perf_counter

import streamlit as st

from commercelens.application.contracts import Investigation, ToolError
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
                evidence, trace, limits = response.evidence, response.trace, response.limits
                if response.status == "error":
                    st.error(response.summary)
                else:
                    st.write(response.summary)
            else:
                evidence = investigate(olist_data(), specification)
                trace = [{"step": "investigate", "duration_ms": round((perf_counter() - started) * 1000, 2)}]
                limits = ["Results describe sampled Olist orders in the selected purchase cohorts."]
            if evidence.calculations:
                calc = evidence.calculations
                unit = calc["unit"]
                current, baseline, change = st.columns(3)
                current.metric("Current", value(calc["current"], unit))
                baseline.metric("Baseline", value(calc["baseline"], unit))
                delta = calc["delta"]
                change.metric("Change", f"{delta * 100:+.2f} pp" if unit == "share" and delta is not None
                              else value(delta, unit))
                st.caption(calc["definition"])
                for label, window in calc["windows"].items():
                    if window and window[0]:
                        st.caption(f"{label.capitalize()} cohort · {window[0]} through {window[1]} (exclusive end)")
                if calc["groups"]:
                    records = [
                        {key: float(val) if isinstance(val, Decimal) else val for key, val in row.items()}
                        for row in calc["groups"]
                    ]
                    if delta is not None:
                        st.bar_chart(records, x="group", y="delta_contribution", horizontal=True)
                    st.dataframe(records, hide_index=True)
                    if calc["omitted_groups"]:
                        st.caption(f"{calc['omitted_groups']} additional groups are included in the totals.")
            elif evidence.result:
                st.dataframe([dict(zip(evidence.result.columns, row)) for row in evidence.result.rows])
            for citation in evidence.citations:
                with st.expander(citation.title):
                    st.write(citation.excerpt)
            for limit in limits:
                st.caption(limit)
            if evidence.sql:
                with st.expander("Executed SQL"):
                    st.code(evidence.sql, language="sql")
            with st.expander("Execution trace"):
                st.json(trace)
        except ToolError as exc:
            st.error(str(exc))
