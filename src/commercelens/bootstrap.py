"""Compose Olist tools and a configured model for the user-facing interfaces."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from commercelens.application.agent.graph import Agent, VARIANTS
from commercelens.application.contracts import ToolError
from commercelens.domain.metrics import RELATIONS
from commercelens.infrastructure.analytics.investigation import investigate
from commercelens.infrastructure.data.readonly import ReadOnlyDuckDB
from commercelens.infrastructure.llm.openai_compatible import OpenAICompatible
from commercelens.infrastructure.retrieval.knowledge import Knowledge


def model_from_env() -> OpenAICompatible:
    url = os.environ.get("COMMERCE_MODEL_URL", "http://127.0.0.1:8080/v1")
    parts = urlsplit(url)
    local = parts.hostname in {"127.0.0.1", "::1", "localhost"}
    if not local and (parts.scheme != "https" or os.environ.get("COMMERCE_ENABLE_REMOTE_MODEL") != "1"):
        raise ToolError("Remote model calls require HTTPS and explicit COMMERCE_ENABLE_REMOTE_MODEL=1")
    return OpenAICompatible(
        url, os.environ.get("COMMERCE_MODEL", "commercelens-local"),
        os.environ.get("COMMERCE_MODEL_API_KEY"), local=local,
    )


def olist_data(path: Path | None = None) -> ReadOnlyDuckDB:
    return ReadOnlyDuckDB(path or Path(os.environ.get("COMMERCE_OLIST_DB", "data/olist.duckdb")), tuple(RELATIONS))


def olist_agent(variant: str = "full", path: Path | None = None) -> Agent:
    return Agent(olist_data(path), model_from_env(), VARIANTS[variant], Knowledge().search, investigate)
