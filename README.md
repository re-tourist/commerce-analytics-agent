# CommerceLens

CommerceLens turns natural-language commerce questions into DuckDB queries and metric investigations. It runs against a reproducible 15,000-order sample of Olist and returns query results, metric definitions, group contributions and an execution trace.

## What you can investigate

| Scenario | Evidence from the Olist sample |
| --- | --- |
| Compare late delivery rates by customer state | July 2018 had 30 late orders out of 936 eligible orders (3.21%). June had 15 of 917 (1.64%), a change of +1.57 percentage points. |
| Compare merchandise value by product category | July 2018 recorded R$141,625.90 in item prices, up R$2,265.52 from June. The report breaks down the change by category. |
| Compare recorded payments by customer state | July 2018 recorded R$166,395.04 in payments, up R$3,679.51 from June. The report uses one payment total per order. |

The sample is historical. Merchandise value excludes freight, and recorded payments are a separate order-level proxy. Seller participation and review-score differences support descriptive comparisons.

## Run locally

Use Python 3.12. The commands below assume the repository root is your working directory.

```sh
python -m pip install -e ".[demo,test,benchmark]"
python scripts/fetch_olist.py
python scripts/build_olist.py
python -m pytest -q
python -m streamlit run app/streamlit_app.py
```

The **Preconfigured metric** option runs live SQL and calculations on the rebuilt sample. For **Natural language**, start a local OpenAI-compatible model server at `http://127.0.0.1:8080/v1` with model alias `commercelens-local`. Use **Download report** to save the query inputs, calculations, SQL, citations and execution trace. See the [model setup](docs/reproduction.md) for the pinned llama.cpp and Qwen configuration used in the evaluation.

```sh
commercelens ask "Compare late delivery rates by customer state for July 2018 versus June 2018."
commercelens metric merchandise_value --group category --start 2018-07-01 --end 2018-08-01
python -m uvicorn commercelens.interfaces.http:app
```

## How it works

The LangGraph workflow gives the model analytical schemas and optional retrieved metric notes. The model proposes a SQL, metric investigation, knowledge or abstention plan. DuckDB runs in read-only mode with external access disabled. The investigation tool calculates totals and group contributions in Python, and verification checks result bounds and reconciliation. The response includes SQL, evidence and the tools that ran.

In the 45-question Olist regression benchmark, the SQL baseline passed 28 cases, SQL + RAG passed 41, and the full agent passed 40. All used the same local Qwen model. See the report for the adapted DataBench subset, error analysis and latency.

- [Architecture and metric contracts](docs/architecture.md)
- [Reproduction and model setup](docs/reproduction.md)
- [Evaluation protocol](docs/evaluation.md)
- [Results and limitations](reports/acceptance.md)

Olist is published under CC BY-NC-SA 4.0. Download the source through the publisher link. [Olist on Kaggle](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)
