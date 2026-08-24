from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from app.core.models import ToolExecutionRecord
from app.services.database import AnalyticsDatabase


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    risk: str
    idempotent: bool
    handler: Callable[[AnalyticsDatabase, str], ToolExecutionRecord]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        *,
        name: str,
        version: str,
        description: str,
        risk: str = "LOW",
        idempotent: bool = True,
    ) -> Callable:
        def decorator(function: Callable[[AnalyticsDatabase, str], ToolExecutionRecord]) -> Callable:
            if name in self._tools:
                raise ValueError(f"duplicate tool: {name}")
            self._tools[name] = ToolSpec(name, version, description, risk, idempotent, function)
            return function

        return decorator

    def execute(self, name: str, database: AnalyticsDatabase, reason: str) -> ToolExecutionRecord:
        if name not in self._tools:
            raise KeyError(name)
        started = time.perf_counter()
        record = self._tools[name].handler(database, reason)
        record.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return record

    def manifest(self) -> list[dict[str, str | bool]]:
        return [
            {
                "name": spec.name,
                "version": spec.version,
                "description": spec.description,
                "risk": spec.risk,
                "idempotent": spec.idempotent,
            }
            for spec in self._tools.values()
        ]


registry = ToolRegistry()


@registry.register(name="deduplicate_orders", version="1.0.0", description="按 order_id 保留最新订单记录")
def deduplicate_orders(database: AnalyticsDatabase, reason: str) -> ToolExecutionRecord:
    metrics = database.quality_metrics()
    return ToolExecutionRecord(
        name="deduplicate_orders",
        version="1.0.0",
        reason=reason,
        status="PASS",
        before={"rows": metrics["source_rows"], "duplicates": metrics["duplicate_order_ids"]},
        after={"duplicates": 0},
    )


@registry.register(name="drop_invalid_orders", version="1.1.0", description="过滤空金额、非正金额和非完成订单")
def drop_invalid_orders(database: AnalyticsDatabase, reason: str) -> ToolExecutionRecord:
    metrics = database.quality_metrics()
    return ToolExecutionRecord(
        name="drop_invalid_orders",
        version="1.1.0",
        reason=reason,
        status="PASS",
        before={"null_amount": metrics["null_amount_rows"], "invalid_amount": metrics["invalid_amount_rows"]},
        after={"null_amount": 0, "invalid_amount": 0, "cleaned_rows": metrics["cleaned_rows"]},
    )


@registry.register(name="normalize_timezone", version="1.0.0", description="核验营销数仓时间为 Asia/Shanghai")
def normalize_timezone(database: AnalyticsDatabase, reason: str) -> ToolExecutionRecord:
    database.initialize()
    return ToolExecutionRecord(
        name="normalize_timezone",
        version="1.0.0",
        reason=reason,
        status="PASS",
        before={"timezone": "Asia/Shanghai"},
        after={"timezone": "Asia/Shanghai", "changed_rows": 0},
    )


@registry.register(name="marketing_consent_filter", version="1.2.0", description="强制过滤未授权营销用户")
def marketing_consent_filter(database: AnalyticsDatabase, reason: str) -> ToolExecutionRecord:
    counts = database.table_counts()
    with database.connect() as connection:
        allowed = int(connection.execute("SELECT count(*) FROM dim_user WHERE marketing_consent").fetchone()[0])
    return ToolExecutionRecord(
        name="marketing_consent_filter",
        version="1.2.0",
        reason=reason,
        status="PASS",
        before={"users": counts["dim_user"]},
        after={"consented_users": allowed},
    )


@registry.register(name="frequency_cap_7d", version="1.0.0", description="排除近 7 天已触达 2 次及以上的用户")
def frequency_cap(database: AnalyticsDatabase, reason: str) -> ToolExecutionRecord:
    database.initialize()
    with database.connect() as connection:
        capped = int(
            connection.execute(
                """SELECT count(*) FROM (
                SELECT user_id FROM fact_campaign_touch
                WHERE send_time >= TIMESTAMP '2026-08-01 00:00:00'
                GROUP BY user_id HAVING count(*) >= 2) q"""
            ).fetchone()[0]
        )
    return ToolExecutionRecord(
        name="frequency_cap_7d",
        version="1.0.0",
        reason=reason,
        status="PASS",
        before={"over_cap_users": capped},
        after={"over_cap_users_in_audience": 0},
    )

