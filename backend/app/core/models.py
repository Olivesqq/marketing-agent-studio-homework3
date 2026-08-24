from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    offline = "offline"
    online = "online"


class ProviderName(str, Enum):
    openai = "openai"
    qwen = "qwen"
    deepseek = "deepseek"


class PromptVersion(str, Enum):
    v1_baseline = "v1_baseline"
    v2_grounded = "v2_grounded"
    v3_critique_repair = "v3_critique_repair"


class RunStatus(str, Enum):
    queued = "QUEUED"
    running = "RUNNING"
    paused = "PAUSED_REVIEW"
    completed = "COMPLETED"
    blocked = "BLOCKED"
    failed = "FAILED"
    rejected = "REJECTED"


class RunRequest(BaseModel):
    goal: str = Field(min_length=4, max_length=3000)
    mode: RunMode = RunMode.offline
    scenario: str | None = None
    relative_lift: float = Field(default=0.05, gt=0, le=1)
    connection_id: str | None = Field(default=None, max_length=80)
    prompt_version: PromptVersion = PromptVersion.v3_critique_repair


class LoginRequest(BaseModel):
    access_code: str = Field(min_length=4, max_length=128)


class ModelConnectionRequest(BaseModel):
    provider: ProviderName
    api_key: str = Field(min_length=8, max_length=512)
    model: str | None = Field(default=None, min_length=2, max_length=100)


class ModelConnectionResponse(BaseModel):
    connection_id: str
    provider: ProviderName
    model: str
    expires_at: datetime
    key_fingerprint: str
    storage: Literal["memory_only"] = "memory_only"


class ModelCallRecord(BaseModel):
    agent: str
    provider: ProviderName
    model: str
    prompt_version: PromptVersion
    latency_ms: float
    output_valid: bool
    repair_count: int = 0
    error: str | None = None


class CampaignBrief(BaseModel):
    scenario: str
    business_goal: str
    audience_definition: str
    target_metric: str
    target_lift: float
    lift_type: Literal["relative", "percentage_point"] = "relative"
    time_window: str
    channel: str
    assumptions: list[str] = []


class KnowledgeCitation(BaseModel):
    document_id: str
    section: str
    summary: str
    source_id: str | None = None
    publisher: str | None = None
    url: str | None = None
    trust_level: Literal["internal", "official", "community"] = "internal"
    retrieval_score: float = 0


class WorkflowEvent(BaseModel):
    id: int | None = None
    run_id: str
    event: str
    stage: str
    status: str
    title: str
    detail: str
    data: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolExecutionRecord(BaseModel):
    name: str
    version: str
    reason: str
    status: Literal["PASS", "WARN", "FAIL"]
    before: dict[str, int | float | str] = {}
    after: dict[str, int | float | str] = {}
    latency_ms: float = 0


class DataQualityReport(BaseModel):
    source_rows: int
    duplicate_order_ids: int
    null_amount_rows: int
    invalid_amount_rows: int
    cleaned_rows: int
    quality_score: float
    selected_tools: list[ToolExecutionRecord]


class SQLArtifact(BaseModel):
    dialect: str = "duckdb"
    sql: str
    explain: str
    audience_count: int
    preview: list[dict[str, Any]]
    attempts: int
    repair_history: list[str] = []


class CopyRound(BaseModel):
    round: int
    draft: str
    reviewer_feedback: str
    score: float
    accepted: bool


class CopyVariant(BaseModel):
    variant_id: Literal["A", "B", "C"]
    title: str
    body: str
    strategy: str
    blue_score: float


class ExperimentPlan(BaseModel):
    hypothesis: str
    allocation: dict[str, int]
    primary_metric: str
    guardrail_metrics: list[str]
    duration_days: int
    minimum_sample_size: int


class GuardrailDecision(BaseModel):
    status: Literal["PASS", "BLOCK", "REVIEW"]
    risk_level: Literal["GREEN", "YELLOW", "RED"]
    reasons: list[str]
    checks: dict[str, bool]


class ReviewDecision(BaseModel):
    action: Literal["approve", "reject"]
    reviewer: str = "课程演示审核人"
    comment: str = ""


class RunSnapshot(BaseModel):
    run_id: str
    status: RunStatus
    mode: RunMode
    goal: str
    scenario: str | None = None
    current_stage: str
    created_at: datetime
    updated_at: datetime
    artifacts: dict[str, Any] = {}
    error: str | None = None


class KnowledgeSource(BaseModel):
    source_id: str
    title: str
    publisher: str
    url: str | None = None
    published_at: str | None = None
    retrieved_at: str
    trust_level: Literal["internal", "official", "community"]
    content_hash: str


class EvalRequest(BaseModel):
    prompt_versions: list[PromptVersion] = [
        PromptVersion.v1_baseline,
        PromptVersion.v2_grounded,
        PromptVersion.v3_critique_repair,
    ]
    case_limit: int = Field(default=10, ge=1, le=10)


class EvalScore(BaseModel):
    prompt_version: PromptVersion
    total_score: float
    structure_pass_rate: float
    sql_pass_rate: float
    citation_hit_rate: float
    compliance_pass_rate: float
    cases: int
    recommendation: str
