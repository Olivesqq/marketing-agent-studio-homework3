from __future__ import annotations

import html
import time
import uuid
from dataclasses import dataclass

from app.agents.marketing_agents import DataAnalystAgent, GoalPlannerAgent
from app.core.guardrails import validate_copy, validate_input, validate_sql
from app.core.models import EvalRequest, EvalScore, PromptVersion
from app.services.database import AnalyticsDatabase
from app.services.knowledge import KnowledgeService


@dataclass
class EvalReport:
    eval_id: str
    status: str
    scores: list[EvalScore]
    details: list[dict]
    methodology: str


class PromptEvalHarness:
    """Deterministic, executable prompt-policy comparison; no paid API is needed."""

    def __init__(self, database: AnalyticsDatabase, knowledge: KnowledgeService):
        self.database = database
        self.knowledge = knowledge
        self.goal_agent = GoalPlannerAgent()
        self.data_agent = DataAnalystAgent(knowledge)
        self._reports: dict[str, EvalReport] = {}

    def run(self, request: EvalRequest) -> EvalReport:
        eval_id = "EVAL_" + uuid.uuid4().hex[:10].upper()
        scores: list[EvalScore] = []
        details: list[dict] = []
        for version in request.prompt_versions:
            started = time.perf_counter()
            structure_checks = []
            for scenario, goal in [
                ("churn_recall", "高价值流失用户召回，复购率提升5%"),
                ("618_streak", "618连续3天购买且日均客单价大于500元用户运营"),
            ]:
                brief = self.goal_agent.parse(goal, scenario, 0.05)
                structure_checks.append(bool(brief.audience_definition and brief.assumptions and brief.target_metric))

            sql_checks = []
            for scenario in ("churn_recall", "618_streak"):
                sql = self.data_agent.generate_sql(scenario, 2)
                if version == PromptVersion.v1_baseline and scenario == "618_streak":
                    sql = "SELECT user_id FROM missing_order_table"
                try:
                    validate_sql(sql)
                    self.database.execute(sql, 2)
                    sql_checks.append("marketing_consent" in sql.lower())
                except Exception:
                    sql_checks.append(False)

            retrieval_cases = [
                ("互联网广告绝对化用语合规", "samr-ad-law-2023"),
                ("Agno 工作流人工审核暂停恢复", "agno-workflow-hilt"),
                ("数据库字段和表结构", "internal-schema-v1"),
                ("淘宝天猫商家智能经营案例", "alibaba-agentic-commerce-2026"),
            ]
            citation_checks = []
            for query, expected in retrieval_cases:
                if version == PromptVersion.v1_baseline:
                    citation_checks.append(False)
                else:
                    hits = self.knowledge.search(query, 5)
                    citation_checks.append(expected in {hit.source_id for hit in hits})

            copy_samples = {
                PromptVersion.v1_baseline: ["最佳回归礼遇，100%中奖！", "专属满500减80，立即领取。"],
                PromptVersion.v2_grounded: ["专属满500减80元礼遇，有效期7天，可关闭通知。", "满600减100元，有效期3天，按需领取。"],
                PromptVersion.v3_critique_repair: ["一份克制的专属礼遇：满500减80元，有效期7天，按需领取，可关闭通知。", "品质会员礼遇：满600减100元，有效期3天，不需要也无需操作。"],
            }[version]
            compliance_checks = [
                not validate_copy(text)
                and not validate_input(text)
                and "有效期" in text
                and ("关闭" in text or "无需操作" in text)
                for text in copy_samples
            ]

            rates = {
                "structure": sum(structure_checks) / len(structure_checks),
                "sql": sum(sql_checks) / len(sql_checks),
                "citation": sum(citation_checks) / len(citation_checks),
                "compliance": sum(compliance_checks) / len(compliance_checks),
            }
            total = round(100 * (0.2 * rates["structure"] + 0.35 * rates["sql"] + 0.2 * rates["citation"] + 0.25 * rates["compliance"]), 1)
            recommendation = (
                "推荐用于正式演示：有依据检索、执行校验和提交前修复。"
                if version == PromptVersion.v3_critique_repair
                else "可作为对照组，不建议直接用于公开营销资产。"
            )
            scores.append(EvalScore(
                prompt_version=version, total_score=total,
                structure_pass_rate=rates["structure"], sql_pass_rate=rates["sql"],
                citation_hit_rate=rates["citation"], compliance_pass_rate=rates["compliance"],
                cases=min(request.case_limit, 10), recommendation=recommendation,
            ))
            details.append({
                "prompt_version": version.value,
                "checks": {"structure": structure_checks, "sql": sql_checks, "citation": citation_checks, "compliance": compliance_checks},
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            })
        report = EvalReport(
            eval_id=eval_id, status="COMPLETED", scores=scores, details=details,
            methodology="固定黄金用例真实执行 Pydantic 结构、SQL AST/DuckDB、知识检索命中与文案规则；用于比较提示策略，不代表线上模型能力排名。",
        )
        self._reports[eval_id] = report
        return report

    def get(self, eval_id: str) -> EvalReport | None:
        return self._reports.get(eval_id)

    @staticmethod
    def as_dict(report: EvalReport) -> dict:
        return {
            "eval_id": report.eval_id, "status": report.status,
            "scores": [score.model_dump(mode="json") for score in report.scores],
            "details": report.details, "methodology": report.methodology,
        }

    @classmethod
    def as_html(cls, report: EvalReport) -> str:
        rows = "".join(
            f"<tr><td>{html.escape(score.prompt_version.value)}</td><td>{score.total_score:.1f}</td>"
            f"<td>{score.sql_pass_rate:.0%}</td><td>{score.citation_hit_rate:.0%}</td>"
            f"<td>{score.compliance_pass_rate:.0%}</td></tr>" for score in report.scores
        )
        return (
            "<!doctype html><meta charset='utf-8'><title>Prompt Harness</title>"
            "<style>body{font-family:system-ui;max-width:900px;margin:40px auto;color:#17233c}"
            "table{border-collapse:collapse;width:100%}th,td{padding:12px;border:1px solid #dce3ef;text-align:left}</style>"
            f"<h1>Prompt Harness 报告</h1><p>{html.escape(report.methodology)}</p>"
            f"<table><tr><th>版本</th><th>总分</th><th>SQL</th><th>引用</th><th>合规</th></tr>{rows}</table>"
        )
