# Marketing Agent Studio｜电商营销多智能体系统

本项目是一套可真实运行、可复现、可审计的电商营销多智能体系统。系统以 Vue 3、FastAPI、Agno、DuckDB 与 SQLite 为技术底座，将模糊营销目标转化为可执行的客群 SQL、数据治理记录、A/B/C 文案、实验方案和安全决策。它不是页面动画：SQL、清洗、护栏、自优化重试和人工审核均由后端真实执行。

## 适用问题与业务价值

电商运营常见的困难不是“能否生成一句文案”，而是如何把人群定义、数据口径、合规要求、实验设计和执行审计连成闭环。本系统用八个角色完成这条链路，降低字段臆造、违规触达、口径不一致和不可复现等风险。

两个贯穿案例为：

1. 高价值流失召回：圈选流失分不低于 0.70、近 180 天客单价不低于 500 元、具有营销授权且未超频的用户，目标是使 30 天复购率相对提升 5%。固定数据集圈选 6,507 人。
2. 618 连续购买运营：识别大促期连续至少 3 天购买且日均客单价大于 500 元的用户，设计低打扰承接方案。固定数据集圈选 2,069 人。

另提供 SQL 自修复、57,000 人超大客群人工审核、危险 SQL、违规文案、提示词注入和敏感信息输入等安全案例。

## 八个角色如何协作

| 角色 | 负责内容 | 可验证产物 |
|---|---|---|
| `GoalPlannerAgent` | 补全人群、周期、KPI、渠道和假设 | `CampaignBrief` |
| `DataAnalystAgent` | 基于知识库生成 DuckDB SQL | SQL、EXPLAIN、人数、样例 |
| `DataQualityAgent` | 根据质量指标选择注册工具 | 工具版本、原因、前后指标 |
| `ExperimentAgent` | 设计 A/B/C 分流和指标 | 假设、样本量、主指标、护栏 |
| `RedCopyAgent` | 生成高转化候选文案 | 每轮草案 |
| `BlueReviewAgent` | 评审真实性、体验和合规 | 反馈、评分、最终变体 |
| `Guardrail` | 检查输入、SQL、隐私、授权、频控、规模和文案 | PASS / REVIEW / BLOCK |
| `WorkflowEngine` | 固定顺序、有限重试、暂停和恢复 | SSE 事件、SQLite 状态、审计记录 |

Agent 负责判断和生成，确定性工作流负责顺序、最大重试次数和不可绕过的安全检查。页面只展示任务依据、工具调用、验证结果、重试原因和决策摘要，不展示模型隐藏思维链。

## 真实数据与知识底座

- DuckDB 生成 60,000 名合成用户、247,000 行订单、180,000 行行为和 90,000 行触达记录。
- 原始订单故意包含 400 个重复订单号、240 条空金额和 194 条非正金额，用于验证数据治理不是模拟。
- 知识库包含 4 份内部口径文档和 4 份官方来源摘要，覆盖数据库结构、指标定义、DuckDB 查询、营销合规、淘宝天猫智能经营、Agno HITL 和在线模型接入。
- 检索结果返回来源编号、发布机构、原始链接、章节、摘要、内容哈希和检索分，避免模型臆造字段或规则。

## SQL 安全与自优化

SQL 执行前由 `sqlglot` 解析 AST，只允许单条 SELECT/CTE；系统检查表字段白名单，禁止 DDL、DML、多语句和敏感字段。通过后先执行 `EXPLAIN`，再由 DuckDB 真实计算人数和预览。

可修复错误会以机器可读反馈返回 DataAnalyst，例如 `UNKNOWN_TABLE:missing_order_table`。系统最多重试三次；危险 SQL 不重试并直接阻断。演示案例中，错误表名在第二次尝试被修复并收敛到 6,507 人。

## 在线模式：访客自带密钥

在线模式支持 OpenAI、通义千问（DashScope）和 DeepSeek。访客在页面中输入 API Key 后，服务端生成随机 `connection_id`：

- Key 只保存在服务进程内存，默认 30 分钟过期；
- Key 不进入 SQLite、DuckDB、日志、事件、导出文件或浏览器持久化存储；
- 供应商 API 地址固定在服务端白名单，访客不能填写任意 Base URL；
- 六个业务 Agent 均真实调用所选模型并接受 Pydantic 结构校验；
- 调用失败会明确标记失败，不使用离线固定结果伪装在线成功。

公开演示服务不配置共享模型密钥，因此不会产生站点所有者无法控制的模型费用。

## Prompt Harness

“Prompt Lab”对同一组黄金用例执行三种提示策略：

- `v1_baseline`：基础角色指令；
- `v2_grounded`：加入知识依据、字段边界和结构约束；
- `v3_critique_repair`：在知识增强基础上增加提交前自检与修复。

评测真实执行 Pydantic 结构、SQL AST、DuckDB 查询、知识来源命中和文案合规规则，并生成 JSON/HTML 报告。该结果用于比较提示策略，不被表述为线上模型能力排行榜。

## 公开访问安全

公网环境启用：

- 邀请码登录和签名 `HttpOnly`、`Secure`、`SameSite=Strict` Cookie；
- 运行与模型连接按会话隔离，猜到 `run_id` 也不能跨会话读取；
- DLP 拦截常见 API Key、密码、邮箱、手机号、身份证和通过 Luhn 校验的银行卡号；
- 写请求限流、单会话并发上限、请求大小限制和模型超时；
- 精确 Origin/CORS/TrustedHost，CSP、HSTS、`X-Frame-Options` 等安全响应头；
- 只使用合成数据，不连接真实发送渠道、支付系统或生产数据库；
- `PUBLIC_DEMO=true` 时若未启用邀请码、HTTPS Cookie 或高熵签名密钥，服务拒绝启动。

完整威胁模型和部署检查见 [SECURITY.md](SECURITY.md)。

## 本地一键运行

要求 Python 3.10+、Node.js 20+、npm：

```bash
./setup.sh
./start.sh
```

打开 <http://127.0.0.1:5173>。离线模式不需要任何密钥；SQL、清洗、护栏和数据库仍真实运行。

运行测试：

```bash
./test.sh
```

当前验收基线：19 项后端测试通过，代码覆盖率 81%；Vue 生产构建成功；生产依赖 `npm audit` 为 0 漏洞。

## 公网部署

仓库包含多阶段 `Dockerfile` 和 `render.yaml`。Render 构建 Vue 静态文件后，由同一个 FastAPI 服务同源提供页面和 API。部署时必须配置：

- `DEMO_ACCESS_CODE`：至少 12 位随机邀请码；
- `APP_SIGNING_KEY`：由云平台生成的高熵 Secret；
- `PUBLIC_DEMO=true`、`REQUIRE_INVITE_CODE=true`、`SESSION_COOKIE_SECURE=true`；
- `PUBLIC_ORIGIN` 与 `ALLOWED_HOSTS`：精确设置为实际 HTTPS 域名。

免费实例在无访问时会休眠，首次打开可能需要几十秒唤醒；本地文件系统是临时的，服务重启后运行历史和临时模型连接会丢失，但固定种子合成数据会自动重建。它适合作业演示，不适合作为真实营销生产系统。

## 主要 API

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/v1/auth/login` | 邀请码登录 |
| GET | `/api/v1/session` | 当前会话与公开环境说明 |
| GET | `/api/v1/model-providers` | 在线供应商预设 |
| POST | `/api/v1/model-connections` | 创建内存临时模型连接 |
| POST | `/api/v1/runs` | 创建工作流 |
| GET | `/api/v1/runs/{run_id}/events` | SSE 结构化事件 |
| GET | `/api/v1/runs/{run_id}` | 获取持久化快照 |
| POST | `/api/v1/runs/{run_id}/review` | 批准或驳回暂停任务 |
| GET | `/api/v1/knowledge/sources` | 版本化知识来源 |
| GET | `/api/v1/knowledge/search` | 带分数和链接的检索结果 |
| POST | `/api/v1/evals` | 执行 Prompt 对比 Harness |
| GET | `/health` | 健康检查 |

本地开发模式保留 OpenAPI 文档；公开模式关闭 `/docs`、`/redoc` 和 OpenAPI JSON。

## 项目结构

```text
backend/app/
  agents/marketing_agents.py    六角色在线调用与离线 Fixture
  api/v1.py                     登录、BYOK、REST、SSE、评测与导出
  core/guardrails.py            输入、SQL、隐私与文案规则
  knowledge/                    版本化文档和来源清单
  services/database.py          DuckDB 合成数仓与真实执行
  services/eval_harness.py      Prompt 版本黄金评测
  services/security.py          会话、DLP、限流和内存 Key Vault
  services/state_store.py       SQLite 状态与会话隔离
  services/workflow.py          重试、暂停、恢复和资产编排
frontend/src/components/
  Dashboard.vue                 业务看板、BYOK、知识证据与 Prompt Lab
Dockerfile                      前后端同源云部署
render.yaml                     Render Blueprint 与安全变量
```

## 边界

本项目不声称复现淘宝或天猫内部系统，只依据公开资料把现实电商需求映射到课程要求。系统不处理真实客户数据、不执行真实投放，也不替代法律、隐私或营销合规专业审查。
