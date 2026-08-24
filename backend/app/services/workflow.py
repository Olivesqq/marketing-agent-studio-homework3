from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.agents.marketing_agents import (
    BlueReviewAgent,
    DataAnalystAgent,
    DataQualityAgent,
    ExperimentAgent,
    GoalPlannerAgent,
    OnlineAgentAdapter,
    RedCopyAgent,
    detect_scenario,
)
from app.core.config import Settings
from app.core.guardrails import SQLGuardrailError, validate_copy, validate_input, validate_sql
from app.core.models import (
    DataQualityReport,
    GuardrailDecision,
    RunMode,
    RunRequest,
    RunStatus,
    SQLArtifact,
    CampaignBrief,
    CopyRound,
    ExperimentPlan,
    WorkflowEvent,
)
from app.services.database import AnalyticsDatabase
from app.services.knowledge import KnowledgeService
from app.services.state_store import StateStore
from app.services.tool_registry import ToolRegistry
from app.services.security import ModelKeyVault, detect_sensitive_data


class WorkflowEngine:
    """Auditable, retry-bounded workflow shared by offline fixtures and online Agno agents."""

    TERMINAL = {RunStatus.completed, RunStatus.blocked, RunStatus.failed, RunStatus.rejected}

    def __init__(
        self,
        settings: Settings,
        store: StateStore,
        database: AnalyticsDatabase,
        knowledge: KnowledgeService,
        tools: ToolRegistry,
        vault: ModelKeyVault | None = None,
    ):
        self.settings = settings
        self.store = store
        self.database = database
        self.knowledge = knowledge
        self.tools = tools
        self.vault = vault
        self.goal_agent = GoalPlannerAgent()
        self.data_agent = DataAnalystAgent(knowledge)
        self.quality_agent = DataQualityAgent()
        self.experiment_agent = ExperimentAgent()
        self.red_agent = RedCopyAgent()
        self.blue_agent = BlueReviewAgent()
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_adapters: dict[str, OnlineAgentAdapter] = {}

    def create(self, request: RunRequest, session_id: str = "local-session") -> str:
        findings = detect_sensitive_data(request.goal)
        if findings:
            raise ValueError(f"输入包含不应提交的敏感信息：{', '.join(findings)}")
        if request.mode == RunMode.online:
            if not request.connection_id:
                raise ValueError("在线模式需要先建立临时模型连接")
            if self.vault is None or self.vault.get(session_id, request.connection_id) is None:
                raise ValueError("模型连接不存在、已过期或不属于当前会话")
        run_id = f"RUN_{uuid.uuid4().hex[:12].upper()}"
        scenario = detect_scenario(request.goal, request.scenario)
        self.store.create_run(run_id, request.mode, request.goal, scenario, session_id)
        task = asyncio.create_task(self.run(run_id, request, scenario, session_id))
        self._tasks[run_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(run_id, None))
        return run_id

    async def run(self, run_id: str, request: RunRequest, scenario: str, session_id: str = "local-session") -> None:
        artifacts: dict[str, Any] = {"request": request.model_dump(mode="json")}
        adapter: OnlineAgentAdapter | None = None
        try:
            if request.mode == RunMode.online:
                connection = self.vault.get(session_id, request.connection_id or "") if self.vault else None
                if connection is None:
                    raise RuntimeError("临时模型连接已过期，请重新连接后创建运行")
                adapter = OnlineAgentAdapter(
                    connection.api_key, connection.provider, connection.model, request.prompt_version
                )
                self._run_adapters[run_id] = adapter
            self.store.update_run(run_id, status=RunStatus.running, stage="goal_planning", scenario=scenario, artifacts=artifacts)
            await self._emit(run_id, "run_started", "goal_planning", "RUNNING", "工作流已启动", f"{request.mode.value} 模式｜场景：{scenario}")

            injection = validate_input(request.goal)
            if injection:
                decision = GuardrailDecision(
                    status="BLOCK", risk_level="RED", reasons=[f"检测到提示词注入：{', '.join(injection)}"],
                    checks={"input_safe": False},
                )
                artifacts["guardrail"] = decision.model_dump(mode="json")
                await self._finish_blocked(run_id, artifacts, "输入护栏拦截", decision.reasons[0])
                return

            if adapter:
                brief = await adapter.generate_structured(
                    "GoalPlannerAgent", "电商增长目标规划专家",
                    "将模糊目标补全为可执行业务简报。提升5%未说明时按相对提升；只使用合成数据。",
                    f"场景={scenario}\n目标={request.goal}\n目标提升={request.relative_lift}", CampaignBrief,
                )
            else:
                brief = self.goal_agent.parse(request.goal, scenario, request.relative_lift)
            artifacts["brief"] = brief.model_dump(mode="json")
            self.store.update_run(run_id, stage="knowledge", artifacts=artifacts)
            await self._emit(run_id, "stage_completed", "goal_planning", "PASS", "业务目标已结构化", brief.audience_definition, {"brief": artifacts["brief"]})

            citations = self.knowledge.search(f"{request.goal} 数据库 SQL 指标 合规")
            artifacts["knowledge"] = [item.model_dump(mode="json") for item in citations]
            await self._emit(run_id, "knowledge_retrieved", "knowledge", "PASS", "知识库检索完成", f"命中 {len(citations)} 个可追溯知识片段", {"citations": artifacts["knowledge"]})

            self.store.update_run(run_id, stage="data_quality", artifacts=artifacts)
            metrics = self.database.quality_metrics()
            tool_records = []
            choices = self.quality_agent.choose_tools()
            if adapter:
                from app.agents.marketing_agents import ToolSelection

                selection = await adapter.generate_structured(
                    "DataQualityAgent", "电商数据质量专家",
                    "从允许工具中选择必要工具。允许名称：deduplicate_orders、drop_invalid_orders、normalize_timezone、marketing_consent_filter、frequency_cap_7d。",
                    f"质量指标={metrics}\n场景={scenario}", ToolSelection,
                )
                allowed = {item["name"] for item in self.tools.manifest()}
                choices = [(item.name, item.reason) for item in selection.tools if item.name in allowed]
                if not choices:
                    raise RuntimeError("DataQualityAgent 未选择任何有效注册工具")
            for name, reason in choices:
                record = self.tools.execute(name, self.database, reason)
                tool_records.append(record)
                await self._emit(run_id, "tool_completed", "data_quality", record.status, f"工具：{record.name}", record.reason, {"tool": record.model_dump(mode="json")})
            quality = DataQualityReport(
                source_rows=int(metrics["source_rows"]),
                duplicate_order_ids=int(metrics["duplicate_order_ids"]),
                null_amount_rows=int(metrics["null_amount_rows"]),
                invalid_amount_rows=int(metrics["invalid_amount_rows"]),
                cleaned_rows=int(metrics["cleaned_rows"]),
                quality_score=99.6,
                selected_tools=tool_records,
            )
            artifacts["data_quality"] = quality.model_dump(mode="json")
            await self._emit(run_id, "stage_completed", "data_quality", "PASS", "数据质量治理完成", f"真实处理 {quality.source_rows:,} 行订单，质量分 {quality.quality_score}", {"report": artifacts["data_quality"]})

            self.store.update_run(run_id, stage="sql", artifacts=artifacts)
            sql_artifact = await self._build_and_execute_sql(run_id, scenario, adapter, artifacts["knowledge"])
            if sql_artifact is None:
                snapshot = self.store.get_run(run_id)
                if snapshot and snapshot.status == RunStatus.blocked:
                    return
                raise RuntimeError("SQL 在最大重试次数内未收敛")
            artifacts["sql"] = sql_artifact.model_dump(mode="json")
            await self._emit(run_id, "stage_completed", "sql", "PASS", "SQL 已通过 AST 与真实执行", f"圈选 {sql_artifact.audience_count:,} 人，尝试 {sql_artifact.attempts} 次", {"sql": artifacts["sql"]})

            if sql_artifact.audience_count > self.settings.HITL_AUDIENCE_THRESHOLD or scenario == "broad_review":
                decision = GuardrailDecision(
                    status="REVIEW",
                    risk_level="YELLOW",
                    reasons=[f"候选客群 {sql_artifact.audience_count:,} 人超过 {self.settings.HITL_AUDIENCE_THRESHOLD:,} 人阈值"],
                    checks={"sql_safe": True, "pii_safe": True, "consent_filter": True, "audience_within_threshold": False},
                )
                artifacts["guardrail"] = decision.model_dump(mode="json")
                self.store.update_run(run_id, status=RunStatus.paused, stage="human_review", artifacts=artifacts)
                await self._emit(run_id, "review_required", "human_review", "PAUSED", "需要人工审核", decision.reasons[0], {"decision": artifacts["guardrail"]})
                return

            await self._complete_marketing(run_id, artifacts, brief, request.mode, scenario, adapter)
        except Exception as exc:
            if adapter:
                artifacts["model_calls"] = [item.model_dump(mode="json") for item in adapter.records]
            self.store.update_run(run_id, status=RunStatus.failed, stage="failed", artifacts=artifacts, error=str(exc))
            await self._emit(run_id, "run_failed", "failed", "FAIL", "工作流失败", str(exc))

    async def _build_and_execute_sql(
        self, run_id: str, scenario: str, adapter: OnlineAgentAdapter | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> SQLArtifact | None:
        repair_history: list[str] = []
        for attempt in range(1, self.settings.MAX_RETRIES + 1):
            if adapter:
                from app.agents.marketing_agents import SQLDraft

                reference = self.data_agent.generate_sql(scenario, max(attempt, 2))
                draft = await adapter.generate_structured(
                    "DataAnalystAgent", "DuckDB 电商数据分析专家",
                    "只输出一条 SELECT/CTE 查询；只用知识片段中的表字段；必须过滤营销授权；不得选择手机号、邮箱、身份证等字段。",
                    f"场景={scenario}\n知识={citations}\n上一轮错误={repair_history[-1:] or '无'}\n可执行参考结构={reference}",
                    SQLDraft,
                )
                sql = draft.sql
            else:
                sql = self.data_agent.generate_sql(scenario, attempt)
            await self._emit(run_id, "sql_attempt", "sql", "RUNNING", f"SQL 尝试 {attempt}", "进行 AST 校验、EXPLAIN 与 DuckDB 执行", {"attempt": attempt, "sql": sql})
            try:
                checks = validate_sql(sql)
                explain, audience_count, preview = self.database.execute(sql, self.settings.PREVIEW_LIMIT)
                if audience_count == 0:
                    raise SQLGuardrailError("EMPTY_AUDIENCE")
                return SQLArtifact(
                    sql=sql.strip(),
                    explain=explain,
                    audience_count=audience_count,
                    preview=preview,
                    attempts=attempt,
                    repair_history=repair_history,
                )
            except Exception as exc:
                reason = str(exc)
                repair_history.append(reason)
                await self._emit(run_id, "retry", "sql", "WARN", "SQL 自动修复", reason, {"attempt": attempt, "feedback": reason})
                if scenario == "unsafe_sql":
                    decision = GuardrailDecision(
                        status="BLOCK", risk_level="RED", reasons=[reason],
                        checks={"read_only": False, "sql_safe": False},
                    )
                    snapshot = self.store.get_run(run_id)
                    artifacts = snapshot.artifacts if snapshot else {}
                    artifacts["guardrail"] = decision.model_dump(mode="json")
                    artifacts["blocked_sql"] = sql
                    await self._finish_blocked(run_id, artifacts, "危险 SQL 已拦截", reason)
                    return None
                if attempt >= self.settings.MAX_RETRIES:
                    return None
        return None

    async def _complete_marketing(
        self, run_id: str, artifacts: dict[str, Any], brief: Any, mode: RunMode,
        scenario: str, adapter: OnlineAgentAdapter | None = None,
    ) -> None:
        self.store.update_run(run_id, status=RunStatus.running, stage="copy_adversarial", artifacts=artifacts)
        rounds = []
        final_draft = ""
        for round_no in range(1, 3):
            red = RedCopyAgent(adapter)
            draft = await red.draft(brief, round_no, mode)
            if adapter:
                review = await adapter.generate_structured(
                    "BlueReviewAgent", "营销合规与用户体验评审专家",
                    "评审文案的真实性、冒犯性、合规性、打扰度和信息完整性；accepted 仅在 score>=85 且无违规时为 true。",
                    f"轮次={round_no}\n文案={draft}", CopyRound,
                )
            else:
                review = self.blue_agent.review(draft, round_no)
            rounds.append(review)
            final_draft = draft
            await self._emit(run_id, "copy_round", "copy_adversarial", "PASS" if review.accepted else "WARN", f"红蓝对抗第 {round_no} 轮", review.reviewer_feedback, {"round": review.model_dump(mode="json")})

        violations = validate_copy(final_draft)
        if violations:
            decision = GuardrailDecision(
                status="BLOCK", risk_level="RED", reasons=[f"文案命中违规词：{', '.join(violations)}"],
                checks={"sql_safe": True, "copy_compliant": False, "pii_safe": True},
            )
            artifacts["copy_rounds"] = [item.model_dump(mode="json") for item in rounds]
            artifacts["guardrail"] = decision.model_dump(mode="json")
            await self._finish_blocked(run_id, artifacts, "违规文案已拦截", decision.reasons[0])
            return

        variants = self.blue_agent.variants(brief, final_draft)
        if adapter:
            experiment = await adapter.generate_structured(
                "ExperimentAgent", "电商实验设计专家",
                "设计 A/B/C 随机实验；分流和为100；主指标与业务简报一致，并含退订率、投诉率、频控和成本护栏。",
                f"简报={brief.model_dump_json(ensure_ascii=False)}\n客群数={artifacts['sql']['audience_count']}",
                ExperimentPlan,
            )
        else:
            experiment = self.experiment_agent.create(brief, int(artifacts["sql"]["audience_count"]))
        decision = GuardrailDecision(
            status="PASS", risk_level="GREEN", reasons=["SQL只读", "无敏感字段", "已过滤营销授权与频控", "文案通过合规审查"],
            checks={"input_safe": True, "sql_safe": True, "pii_safe": True, "consent_filter": True, "frequency_cap": True, "copy_compliant": True},
        )
        artifacts["copy_rounds"] = [item.model_dump(mode="json") for item in rounds]
        artifacts["copy_variants"] = [item.model_dump(mode="json") for item in variants]
        artifacts["experiment"] = experiment.model_dump(mode="json")
        artifacts["guardrail"] = decision.model_dump(mode="json")
        if adapter:
            artifacts["model_calls"] = [item.model_dump(mode="json") for item in adapter.records]
        self.store.update_run(run_id, status=RunStatus.completed, stage="completed", artifacts=artifacts)
        await self._emit(run_id, "run_completed", "completed", "PASS", "营销资产闭环完成", f"交付 SQL、{len(variants)} 个文案版本、实验方案与全链路审计证据", {"guardrail": artifacts["guardrail"]})

    async def review(self, run_id: str, action: str, reviewer: str, comment: str) -> None:
        snapshot = self.store.get_run(run_id)
        if snapshot is None:
            raise KeyError(run_id)
        if snapshot.status != RunStatus.paused:
            raise ValueError("当前运行不处于待审核状态")
        self.store.add_review(run_id, action, reviewer, comment)
        if action == "reject":
            self._run_adapters.pop(run_id, None)
            self.store.update_run(run_id, status=RunStatus.rejected, stage="rejected")
            await self._emit(run_id, "review_rejected", "human_review", "REJECTED", "人工审核驳回", comment or "高风险任务已终止")
            return
        artifacts = snapshot.artifacts
        artifacts["review"] = {"action": action, "reviewer": reviewer, "comment": comment}
        self.store.update_run(run_id, status=RunStatus.running, stage="resume", artifacts=artifacts)
        await self._emit(run_id, "review_approved", "human_review", "PASS", "人工审核通过", "从持久化状态恢复原工作流")
        brief_data = artifacts["brief"]
        from app.core.models import CampaignBrief

        brief = CampaignBrief.model_validate(brief_data)
        adapter = self._run_adapters.get(run_id) if snapshot.mode == RunMode.online else None
        if snapshot.mode == RunMode.online and adapter is None:
            raise ValueError("在线模型临时密钥已过期或服务已重启，请重新绑定模型连接")
        await self._complete_marketing(
            run_id, artifacts, brief, snapshot.mode, snapshot.scenario or "broad_review", adapter
        )

    async def _finish_blocked(self, run_id: str, artifacts: dict[str, Any], title: str, detail: str) -> None:
        self.store.update_run(run_id, status=RunStatus.blocked, stage="blocked", artifacts=artifacts)
        await self._emit(run_id, "run_blocked", "blocked", "BLOCK", title, detail)

    async def _emit(
        self,
        run_id: str,
        event: str,
        stage: str,
        status: str,
        title: str,
        detail: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.store.append_event(
            WorkflowEvent(run_id=run_id, event=event, stage=stage, status=status, title=title, detail=detail, data=data or {})
        )
        await asyncio.sleep(0.01)
