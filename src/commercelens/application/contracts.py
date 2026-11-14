from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

Scalar = str | int | float | bool | None


class ToolError(ValueError):
    """A user-safe failure raised by an application tool."""


@dataclass(frozen=True)
class Query:
    columns: list[str]
    rows: list[list[Scalar]]
    truncated: bool = False


class DataTool(Protocol):
    def query(self, sql: str) -> Query: ...
    def schema(self) -> dict[str, list[tuple[str, str]]]: ...


@dataclass(frozen=True)
class Citation:
    id: str
    title: str
    excerpt: str


@dataclass(frozen=True)
class Investigation:
    metric: str
    group: str | None = None
    start: date | None = None
    end: date | None = None
    baseline_start: date | None = None
    baseline_end: date | None = None
    limit: int = 10


@dataclass(frozen=True)
class Plan:
    tool: Literal["sql", "investigate", "knowledge", "unsupported"]
    sql: str | None = None
    investigation: Investigation | None = None
    reason: str = ""


@dataclass(frozen=True)
class ModelCall:
    plan: Plan
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class Planner(Protocol):
    name: str

    def plan(self, prompt: str, question: str) -> ModelCall: ...


@dataclass
class Evidence:
    sql: str | None = None
    result: Query | None = None
    calculations: dict = field(default_factory=dict)
    citations: list[Citation] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


@dataclass
class Answer:
    status: str
    tool: str
    summary: str
    evidence: Evidence
    limits: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    model_usage: list[dict] = field(default_factory=list)
    failure: str | None = None
    model_explanation: str | None = None
    unconfirmed: list[str] = field(default_factory=list)
