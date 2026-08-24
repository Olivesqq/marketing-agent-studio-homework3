import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app, frontend


def test_health_and_public_manifests():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        payload = health.json()
        assert payload["status"] == "UP"
        assert payload["analytics"]["tables"]["dim_user"] == 60000
        assert payload["knowledge_documents"] == 8
        tools = client.get("/api/v1/tools").json()["tools"]
        scenarios = client.get("/api/v1/scenarios").json()["scenarios"]
        assert len(tools) >= 5
        assert {item["id"] for item in scenarios} >= {"churn_recall", "618_streak", "unsafe_sql"}


def test_spa_fallback_does_not_mask_disabled_api_docs():
    for path in ("docs", "redoc", "openapi.json", "api/not-found"):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(frontend(path))
        assert exc_info.value.status_code == 404


def test_online_mode_requires_temporary_connection():
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={"goal": "高价值流失用户复购率提升5%", "mode": "online", "scenario": "churn_recall"},
        )
        assert response.status_code == 400
        assert "临时模型连接" in response.json()["detail"]


def test_knowledge_sources_and_prompt_harness():
    with TestClient(app) as client:
        sources = client.get("/api/v1/knowledge/sources")
        assert sources.status_code == 200
        assert any(item["source_id"] == "samr-ad-law-2023" for item in sources.json()["sources"])
        response = client.post("/api/v1/evals", json={"case_limit": 10})
        assert response.status_code == 201
        scores = response.json()["scores"]
        assert scores[-1]["prompt_version"] == "v3_critique_repair"
        assert scores[-1]["total_score"] >= scores[0]["total_score"]
