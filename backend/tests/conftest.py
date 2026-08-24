from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.database import AnalyticsDatabase
from app.services.knowledge import KnowledgeService
from app.services.state_store import StateStore
from app.services.tool_registry import registry
from app.services.workflow import WorkflowEngine


@pytest.fixture(scope="session")
def knowledge_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "knowledge" / "docs"


@pytest.fixture()
def service_bundle(tmp_path: Path, knowledge_dir: Path):
    settings = Settings(
        APP_MODE="offline",
        ANALYTICS_DB=tmp_path / "test.duckdb",
        STATE_DB=tmp_path / "state.sqlite3",
        KNOWLEDGE_DIR=knowledge_dir,
        HITL_AUDIENCE_THRESHOLD=50_000,
        MAX_RETRIES=3,
    )
    database = AnalyticsDatabase(settings.ANALYTICS_DB, settings.DATA_SEED)
    database.initialize()
    store = StateStore(settings.STATE_DB)
    knowledge = KnowledgeService(settings.KNOWLEDGE_DIR)
    engine = WorkflowEngine(settings, store, database, knowledge, registry)
    return settings, database, store, knowledge, engine

