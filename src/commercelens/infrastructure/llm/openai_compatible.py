"""Minimal OpenAI-compatible HTTP planner. No implicit external endpoint."""

from datetime import date
import json
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from commercelens.application.contracts import Investigation, ModelCall, Plan, ToolError


class MetricParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    group: str | None = None
    start: date | None = None
    end: date | None = None
    baseline_start: date | None = None
    baseline_end: date | None = None
    limit: int = Field(default=10, ge=1, le=25)


class ModelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal["sql", "investigate", "knowledge", "unsupported"]
    sql: str | None = None
    investigation: MetricParameters | None = None
    reason: str = ""


class OpenAICompatible:
    def __init__(self, url: str, model: str, api_key: str | None = None, local: bool = False):
        self.name = model
        self.url = url.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.local = local

    def plan(self, prompt: str, question: str) -> ModelCall:
        try:
            response = httpx.post(self.url, headers=self.headers, timeout=120, trust_env=False, json={
                "model": self.name,
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": question}],
                "temperature": 0.0,
                "seed": 741,
                "max_tokens": 384,
                "response_format": {"type": "json_object"},
            })
            response.raise_for_status()
            payload = response.json()
            usage = payload.get("usage") or {}
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise ToolError(f"Model request failed ({type(exc).__name__})") from exc
        try:
            raw = json.loads(payload["choices"][0]["message"]["content"])
            result = ModelPlan.model_validate(raw)
            parameters = Investigation(**result.investigation.model_dump()) if result.investigation else None
            plan = Plan(result.tool, result.sql, parameters, result.reason)
        except (ValueError, TypeError, KeyError, IndexError, ValidationError):
            # Preserve usage for malformed outputs, including failed attempts.
            plan = Plan("unsupported", reason="invalid_model_plan")
        return ModelCall(
            plan, usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0,
            cost_usd=0.0 if self.local else None,
        )
