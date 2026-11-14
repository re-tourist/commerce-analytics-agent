"""Local JSON interface over the same graph and investigation tool as the CLI."""

from dataclasses import asdict
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from commercelens.application.contracts import Investigation, ToolError
from commercelens.bootstrap import olist_agent, olist_data
from commercelens.infrastructure.analytics.investigation import investigate
from commercelens.infrastructure.llm.openai_compatible import MetricParameters


app = FastAPI(title="CommerceLens", version="0.1.0")


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2_000)
    variant: Literal["sql", "sql_rag", "sql_rag_skills", "full"] = "full"


@app.get("/health")
def health():
    try:
        return {"status": "ok", "relations": list(olist_data().schema())}
    except ToolError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/ask")
def ask(request: Question):
    try:
        return jsonable_encoder(asdict(olist_agent(request.variant).run(request.question)))
    except ToolError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/investigate")
def metric(request: MetricParameters):
    try:
        return jsonable_encoder(asdict(investigate(olist_data(), Investigation(**request.model_dump()))))
    except ToolError as exc:
        raise HTTPException(422, str(exc)) from exc
