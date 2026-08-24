from __future__ import annotations

import hashlib
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb


class AnalyticsDatabase:
    """Deterministic DuckDB sandbox with realistic but synthetic commerce data."""

    def __init__(self, path: Path, seed: int = 20260809):
        self.path = path
        self.seed = seed
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.path))

    def initialize(self, force: bool = False) -> None:
        with self._lock, self.connect() as connection:
            exists = connection.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name='dim_user'"
            ).fetchone()[0]
            if exists and not force:
                return
            connection.execute("DROP TABLE IF EXISTS fact_campaign_touch")
            connection.execute("DROP TABLE IF EXISTS fact_user_activity")
            connection.execute("DROP TABLE IF EXISTS fact_order")
            connection.execute("DROP TABLE IF EXISTS dim_offer")
            connection.execute("DROP TABLE IF EXISTS dim_user")
            connection.execute(
                """
                CREATE TABLE dim_user AS
                SELECT
                  'U' || lpad(CAST(i AS VARCHAR), 6, '0') AS user_id,
                  1 + (i % 7) AS vip_level,
                  ['SH_011','BJ_001','GZ_020','SZ_0755','HZ_0571'][1 + (i % 5)] AS geo_city,
                  round(((i * 37 + 11) % 100) / 100.0, 2) AS churn_score,
                  (i % 20 != 0) AS marketing_consent,
                  sha256('mobile-' || CAST(i AS VARCHAR)) AS mobile_hash,
                  DATE '2024-01-01' + CAST(i % 730 AS INTEGER) AS register_date,
                  DATE '2026-07-31' - CAST(i % 210 AS INTEGER) AS last_active_date
                FROM range(1, 60001) t(i)
                """
            )
            connection.execute(
                """
                CREATE TABLE fact_order AS
                WITH generic_orders AS (
                  SELECT
                    'O' || lpad(CAST(i AS VARCHAR), 8, '0') AS order_id,
                    'U' || lpad(CAST(1 + ((i * 17) % 60000) AS VARCHAR), 6, '0') AS user_id,
                    TIMESTAMP '2026-01-01 08:00:00'
                      + (i % 210) * INTERVAL '1 day'
                      + (i % 12) * INTERVAL '1 hour' AS pay_time,
                    CASE
                      WHEN i % 997 = 0 THEN NULL
                      WHEN i % 1231 = 0 THEN -50.0
                      ELSE CAST(50 + ((i * 13) % 1800) AS DECIMAL(12,2))
                    END AS payment_amount,
                    CASE WHEN i % 23 = 0 THEN 'cancelled' ELSE 'completed' END AS order_status,
                    ['数码','家居','食品','服饰','美妆'][1 + (i % 5)] AS category
                  FROM range(1, 240001) t(i)
                ),
                campaign_orders AS (
                  SELECT
                    'S618' || lpad(CAST(user_no AS VARCHAR), 6, '0') || CAST(day_no AS VARCHAR) AS order_id,
                    'U' || lpad(CAST(user_no AS VARCHAR), 6, '0') AS user_id,
                    TIMESTAMP '2026-06-15 10:00:00' + day_no * INTERVAL '1 day' AS pay_time,
                    CAST(520 + (user_no % 240) AS DECIMAL(12,2)) AS payment_amount,
                    'completed' AS order_status,
                    '品质生活' AS category
                  FROM range(1, 2201) u(user_no)
                  CROSS JOIN range(1, 4) d(day_no)
                ),
                duplicate_samples AS (
                  SELECT * FROM generic_orders WHERE CAST(substr(order_id, 2) AS BIGINT) <= 400
                )
                SELECT * FROM generic_orders
                UNION ALL SELECT * FROM campaign_orders
                UNION ALL SELECT * FROM duplicate_samples
                """
            )
            connection.execute(
                """
                CREATE TABLE fact_user_activity AS
                SELECT
                  'E' || lpad(CAST(i AS VARCHAR), 8, '0') AS event_id,
                  'U' || lpad(CAST(1 + ((i * 29) % 60000) AS VARCHAR), 6, '0') AS user_id,
                  TIMESTAMP '2026-05-01 00:00:00'
                    + (i % 100) * INTERVAL '1 day'
                    + (i % 24) * INTERVAL '1 hour' AS event_time,
                  ['page_view','search','add_to_cart','favorite'][1 + (i % 4)] AS event_type
                FROM range(1, 180001) t(i)
                """
            )
            connection.execute(
                """
                CREATE TABLE fact_campaign_touch AS
                SELECT
                  'T' || lpad(CAST(i AS VARCHAR), 8, '0') AS touch_id,
                  'U' || lpad(CAST(1 + ((i * 31) % 60000) AS VARCHAR), 6, '0') AS user_id,
                  'CMP' || CAST(1 + (i % 8) AS VARCHAR) AS campaign_id,
                  ['A','B','C'][1 + (i % 3)] AS variant_id,
                  TIMESTAMP '2026-07-01 09:00:00' + (i % 38) * INTERVAL '1 day' AS send_time,
                  (i % 10 < 9) AS delivered,
                  (i % 10 < 4) AS opened,
                  (i % 10 < 2) AS clicked,
                  (i % 20 = 0) AS converted
                FROM range(1, 90001) t(i)
                """
            )
            connection.execute(
                """
                CREATE TABLE dim_offer (
                  offer_id VARCHAR,
                  offer_name VARCHAR,
                  threshold_amount DECIMAL(12,2),
                  discount_amount DECIMAL(12,2),
                  valid_days INTEGER,
                  cost_cap DECIMAL(12,2)
                )
                """
            )
            connection.executemany(
                "INSERT INTO dim_offer VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("OFF_RECALL_80", "高价值召回券", 500, 80, 7, 80),
                    ("OFF_618_100", "618品质专享券", 600, 100, 3, 100),
                    ("OFF_CONTROL", "无券对照", 0, 0, 0, 0),
                ],
            )
            self._create_clean_views(connection)

    def _create_clean_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE OR REPLACE VIEW clean_order_deduplicated AS
            SELECT order_id, user_id, pay_time, payment_amount, order_status, category
            FROM fact_order
            QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY pay_time DESC) = 1
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE VIEW clean_order_valid AS
            SELECT * FROM clean_order_deduplicated
            WHERE payment_amount IS NOT NULL AND payment_amount > 0 AND order_status = 'completed'
            """
        )

    def table_counts(self) -> dict[str, int]:
        self.initialize()
        with self.connect() as connection:
            return {
                table: int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in ["dim_user", "fact_order", "fact_user_activity", "fact_campaign_touch", "dim_offer"]
            }

    def quality_metrics(self) -> dict[str, int | float]:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                  count(*) AS source_rows,
                  count(*) - count(DISTINCT order_id) AS duplicate_order_ids,
                  count(*) FILTER (WHERE payment_amount IS NULL) AS null_amount_rows,
                  count(*) FILTER (WHERE payment_amount <= 0) AS invalid_amount_rows
                FROM fact_order
                """
            ).fetchone()
            cleaned = connection.execute("SELECT count(*) FROM clean_order_valid").fetchone()[0]
        return {
            "source_rows": int(row[0]),
            "duplicate_order_ids": int(row[1]),
            "null_amount_rows": int(row[2]),
            "invalid_amount_rows": int(row[3]),
            "cleaned_rows": int(cleaned),
        }

    def execute(self, sql: str, preview_limit: int = 10) -> tuple[str, int, list[dict[str, Any]]]:
        self.initialize()
        clean_sql = sql.strip().rstrip(";")
        with self._lock, self.connect() as connection:
            explain_rows = connection.execute(f"EXPLAIN {clean_sql}").fetchall()
            explain = "\n".join(str(row[-1]) for row in explain_rows)
            audience_count = int(connection.execute(f"SELECT count(*) FROM ({clean_sql}) q").fetchone()[0])
            cursor = connection.execute(f"SELECT * FROM ({clean_sql}) q LIMIT {int(preview_limit)}")
            columns = [item[0] for item in cursor.description]
            preview = [
                {column: self._json_value(value) for column, value in zip(columns, row)}
                for row in cursor.fetchall()
            ]
        return explain, audience_count, preview

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    def fingerprint(self) -> str:
        counts = self.table_counts()
        payload = "|".join(f"{key}:{value}" for key, value in sorted(counts.items()))
        return hashlib.sha256(payload.encode()).hexdigest()[:12]
