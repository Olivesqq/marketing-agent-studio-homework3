from __future__ import annotations

import re

import sqlglot
from sqlglot import exp


ALLOWED_TABLES = {
    "dim_user",
    "fact_order",
    "fact_user_activity",
    "fact_campaign_touch",
    "dim_offer",
    "clean_order_deduplicated",
    "clean_order_valid",
}
FORBIDDEN_COLUMNS = {"mobile_hash", "phone", "mobile", "id_card", "address"}
FORBIDDEN_COPY = ["100%中奖", "绝对有效", "免税代购", "规避关税", "最后机会", "偷税", "国家级", "最高级", "最佳"]
INJECTION_MARKERS = ["IGNORE PREVIOUS", "SYSTEM_PROMPT_OVERRIDE", "忽略之前", "泄露系统提示"]


class SQLGuardrailError(ValueError):
    pass


def validate_input(prompt: str) -> list[str]:
    upper = prompt.upper()
    return [marker for marker in INJECTION_MARKERS if marker in upper]


def validate_sql(sql: str) -> dict[str, object]:
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except Exception as exc:
        raise SQLGuardrailError(f"SQL_PARSE_ERROR: {exc}") from exc
    if len(statements) != 1:
        raise SQLGuardrailError("MULTI_STATEMENT_NOT_ALLOWED")
    statement = statements[0]
    if not isinstance(statement, (exp.Select, exp.Union)) and not statement.find(exp.Select):
        raise SQLGuardrailError("ONLY_SELECT_OR_WITH_ALLOWED")
    forbidden_nodes = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Copy)
    for node_type in forbidden_nodes:
        if statement.find(node_type):
            raise SQLGuardrailError(f"FORBIDDEN_SQL_NODE:{node_type.__name__}")
    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    tables = {table.name.lower() for table in statement.find_all(exp.Table) if table.name.lower() not in cte_names}
    unknown = sorted(tables - ALLOWED_TABLES)
    if unknown:
        raise SQLGuardrailError(f"UNKNOWN_TABLE:{','.join(unknown)}")
    selected_columns = {column.name.lower() for column in statement.find_all(exp.Column)}
    sensitive = sorted(selected_columns & FORBIDDEN_COLUMNS)
    if sensitive:
        raise SQLGuardrailError(f"PII_COLUMN_FORBIDDEN:{','.join(sensitive)}")
    return {"tables": sorted(tables), "pii_safe": True, "single_statement": True, "read_only": True}


def validate_copy(text: str) -> list[str]:
    return [term for term in FORBIDDEN_COPY if term.lower() in text.lower()]


def copy_quality_score(text: str) -> float:
    score = 100.0
    score -= 25 * len(validate_copy(text))
    if len(text) > 220:
        score -= 8
    if "有效期" not in text and "限时" not in text:
        score -= 8
    if "专属" not in text and "礼遇" not in text:
        score -= 5
    if re.search(r"手机号|身份证|住址", text):
        score -= 40
    return max(0.0, round(score, 1))
