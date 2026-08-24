from app.agents.marketing_agents import DataAnalystAgent
from app.core.guardrails import SQLGuardrailError, validate_copy, validate_sql


def test_synthetic_data_is_deterministic_and_contains_quality_issues(service_bundle):
    _, database, _, _, _ = service_bundle
    counts = database.table_counts()
    quality = database.quality_metrics()
    assert counts == {
        "dim_user": 60_000,
        "fact_order": 247_000,
        "fact_user_activity": 180_000,
        "fact_campaign_touch": 90_000,
        "dim_offer": 3,
    }
    assert quality["duplicate_order_ids"] == 400
    assert quality["null_amount_rows"] > 0
    assert quality["invalid_amount_rows"] > 0
    assert len(database.fingerprint()) == 12


def test_two_primary_scenarios_execute_real_sql(service_bundle):
    _, database, _, knowledge, _ = service_bundle
    agent = DataAnalystAgent(knowledge)
    churn_sql = agent.generate_sql("churn_recall", 1)
    streak_sql = agent.generate_sql("618_streak", 1)
    assert validate_sql(churn_sql)["read_only"] is True
    assert validate_sql(streak_sql)["pii_safe"] is True
    assert database.execute(churn_sql)[1] == 6507
    assert database.execute(streak_sql)[1] == 2069


def test_knowledge_returns_traceable_sections(service_bundle):
    _, _, _, knowledge, _ = service_bundle
    results = knowledge.search("高流失高客单价用户 SQL 字段与营销合规")
    assert results
    assert all(item.document_id and item.section and item.summary for item in results)
    assert any(item.document_id == "02_metric_definitions" for item in results)


def test_sql_and_copy_guardrails_block_known_attacks():
    for sql in [
        "DELETE FROM dim_user WHERE vip_level > 5",
        "SELECT mobile_hash FROM dim_user",
        "SELECT * FROM unknown_users",
        "SELECT user_id FROM dim_user; SELECT user_id FROM dim_user",
    ]:
        try:
            validate_sql(sql)
        except SQLGuardrailError:
            pass
        else:
            raise AssertionError(f"unsafe SQL passed: {sql}")
    assert validate_copy("免税代购、规避关税，100%中奖") == ["100%中奖", "免税代购", "规避关税"]


def test_dynamic_tool_registry_is_auditable(service_bundle):
    _, database, _, _, engine = service_bundle
    manifest = engine.tools.manifest()
    names = {item["name"] for item in manifest}
    assert {"deduplicate_orders", "drop_invalid_orders", "normalize_timezone", "marketing_consent_filter", "frequency_cap_7d"} <= names
    record = engine.tools.execute("deduplicate_orders", database, "测试动态调用")
    assert record.status == "PASS"
    assert record.before["duplicates"] == 400
    assert record.after["duplicates"] == 0

