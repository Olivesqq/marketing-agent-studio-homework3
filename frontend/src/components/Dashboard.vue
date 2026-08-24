<template>
  <div class="app-shell">
    <div v-if="!authenticated" class="login-overlay">
      <form class="login-card" @submit.prevent="login">
        <div class="brand-mark large">MA</div>
        <p class="section-kicker">INVITE-ONLY DEMO</p>
        <h2>访问电商营销多智能体工作台</h2>
        <p>公开演示仅使用合成数据。请输入课程邀请码；请勿提交真实姓名、手机号、账号密码、银行卡或生产数据。</p>
        <input v-model="inviteCode" type="password" autocomplete="current-password" placeholder="课程邀请码" aria-label="课程邀请码" />
        <button class="primary-button" type="submit">安全进入</button>
        <small v-if="authError" class="auth-error">{{ authError }}</small>
      </form>
    </div>
    <div v-if="session?.public_demo" class="public-banner">公开演示环境 · 仅合成数据 · 自带模型密钥仅在服务器内存保存 30 分钟 · 请勿输入任何真实敏感信息</div>
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark">MA</div>
        <div><p class="eyebrow">MARKETING AGENT STUDIO</p><h1>电商营销多智能体工作台</h1></div>
      </div>
      <div class="top-actions">
        <span :class="['status-pill', health?.status === 'UP' ? 'green' : 'gray']"><span class="dot"></span>{{ health?.status === 'UP' ? '系统就绪' : '连接中' }}</span>
        <span class="mode-pill">{{ mode === 'offline' ? '离线可复现' : connectionId ? '在线已连接' : '在线待连接' }}</span>
        <a v-if="runId" class="text-button" :href="`/api/v1/runs/${runId}/export.md`">导出报告</a>
      </div>
    </header>

    <main class="workspace">
      <aside class="scenario-panel panel">
        <div class="panel-heading"><div><p class="section-kicker">01 / 场景</p><h2>选择演练任务</h2></div><span class="count-chip">{{ scenarios.length }}</span></div>
        <div class="scenario-list">
          <button v-for="item in scenarios" :key="item.id" :class="['scenario-card', { active: selectedScenario === item.id }]" :disabled="isRunning" @click="selectScenario(item)">
            <span :class="['risk-dot', item.risk.toLowerCase()]"></span><span class="scenario-copy"><strong>{{ item.title }}</strong><small>{{ item.risk }}</small></span><span class="chevron">›</span>
          </button>
        </div>
        <div class="infra-card">
          <p>本地证据底座</p>
          <div><strong>{{ formatNumber(health?.analytics?.tables?.dim_user) }}</strong><span>合成用户</span></div>
          <div><strong>{{ formatNumber(health?.analytics?.tables?.fact_order) }}</strong><span>真实执行订单</span></div>
          <div><strong>{{ health?.registered_tools || 0 }}</strong><span>动态工具</span></div>
          <small>数据指纹 {{ health?.analytics?.fingerprint || '—' }}</small>
        </div>
      </aside>

      <section class="main-column">
        <section class="command-panel panel">
          <div class="command-head"><div><p class="section-kicker">02 / 目标</p><h2>从模糊业务目标启动完整闭环</h2></div><div class="mode-switch" aria-label="模型模式"><button :class="{ active: mode === 'offline' }" :disabled="isRunning" @click="mode = 'offline'">离线</button><button :class="{ active: mode === 'online' }" :disabled="isRunning || !health?.online_ready" @click="mode = 'online'">在线</button></div></div>
          <textarea v-model="goal" :disabled="isRunning" rows="3" aria-label="业务目标"></textarea>
          <div v-if="mode === 'online'" class="connection-panel">
            <div class="connection-copy"><strong>访客自带 API Key（BYOK）</strong><small>支持 OpenAI、通义千问与 DeepSeek。密钥不写入数据库、日志或浏览器存储，30 分钟自动过期。</small></div>
            <select v-model="provider" :disabled="!!connectionId"><option v-for="item in providers" :key="item.id" :value="item.id">{{ item.label }}</option></select>
            <input v-model="modelName" :disabled="!!connectionId" placeholder="模型名称（留空用默认值）" aria-label="模型名称" />
            <input v-model="apiKey" :disabled="!!connectionId" type="password" autocomplete="off" placeholder="API Key（页面不持久化）" aria-label="API Key" />
            <button v-if="!connectionId" class="outline-button" :disabled="apiKey.length < 8" @click="connectModel">建立临时连接</button>
            <button v-else class="connected-button" @click="disconnectModel">已连接 {{ connectionMeta?.model }} · 断开</button>
          </div>
          <div class="command-footer"><div class="assumption"><span>默认口径</span>“提升 5%”解释为相对提升，并在业务简报披露</div><button class="primary-button" :disabled="isRunning || goal.trim().length < 4" @click="startRun"><span v-if="isRunning" class="spinner"></span>{{ isRunning ? '智能体协同中' : '启动工作流' }}</button></div>
          <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
        </section>

        <section class="workflow-panel panel">
          <div class="panel-heading compact"><div><p class="section-kicker">03 / 编排</p><h2>八角色可审计工作流</h2></div><div class="run-meta"><span :class="['status-pill', statusTone]">{{ statusLabel }}</span><code v-if="runId">{{ runId }}</code></div></div>
          <div class="step-grid">
            <div v-for="(step, index) in steps" :key="step.id" :class="['step-card', stepState(step.id)]"><span class="step-index">{{ String(index + 1).padStart(2, '0') }}</span><div><strong>{{ step.title }}</strong><small>{{ step.agent }}</small></div><span class="step-state">{{ stepStateLabel(step.id) }}</span></div>
          </div>
        </section>

        <section v-if="snapshot" class="metrics-grid">
          <article class="metric-card panel"><span>候选客群</span><strong>{{ formatNumber(artifacts.sql?.audience_count) }}</strong><small>DuckDB 真实圈选</small></article>
          <article class="metric-card panel"><span>数据质量</span><strong>{{ artifacts.data_quality?.quality_score ?? '—' }}</strong><small>清洗后质量分</small></article>
          <article class="metric-card panel"><span>SQL 尝试</span><strong>{{ artifacts.sql?.attempts ?? '—' }}</strong><small>最多自动重试 3 次</small></article>
          <article class="metric-card panel"><span>安全结论</span><strong :class="guardTone">{{ artifacts.guardrail?.status || '检查中' }}</strong><small>{{ artifacts.guardrail?.risk_level || '—' }} 风险</small></article>
        </section>

        <section v-if="snapshot?.status === 'PAUSED_REVIEW'" class="review-banner">
          <div><p class="section-kicker">HUMAN IN THE LOOP</p><h3>工作流已持久化暂停</h3><p>{{ artifacts.guardrail?.reasons?.[0] }}</p></div>
          <div class="review-actions"><button class="reject-button" @click="submitReview('reject')">驳回并终止</button><button class="approve-button" @click="submitReview('approve')">批准并继续原流程</button></div>
        </section>

        <section class="evidence-panel panel">
          <div class="tabbar" role="tablist"><button v-for="tab in tabs" :key="tab.id" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">{{ tab.label }}</button></div>

          <div v-if="activeTab === 'overview'" class="tab-content two-column">
            <div><h3>业务简报</h3><dl v-if="artifacts.brief" class="definition-list"><template v-for="(value, key) in briefRows" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl><div v-else class="empty-state">启动工作流后，这里展示 Agent 对模糊目标的结构化结果。</div></div>
            <div><h3>知识检索依据</h3><div v-if="artifacts.knowledge?.length" class="citation-list"><article v-for="item in artifacts.knowledge" :key="`${item.document_id}-${item.section}`"><code>{{ item.source_id || item.document_id }}</code><strong>{{ item.section }}</strong><em>{{ item.publisher }} · score {{ item.retrieval_score }}</em><p>{{ item.summary }}</p><a v-if="item.url" :href="item.url" target="_blank" rel="noreferrer">查看官方来源 ↗</a></article></div><div v-else class="empty-state">知识库将返回来源、章节、检索分和摘要，防止模型臆造字段。</div></div>
          </div>

          <div v-else-if="activeTab === 'data'" class="tab-content">
            <div class="subgrid"><div><h3>生产级 SQL</h3><pre class="code-block"><code>{{ artifacts.sql?.sql || '等待 SQL Agent 生成并执行...' }}</code></pre></div><div><h3>真实执行样例</h3><div class="table-wrap" v-if="artifacts.sql?.preview?.length"><table><thead><tr><th v-for="key in previewKeys" :key="key">{{ key }}</th></tr></thead><tbody><tr v-for="(row, i) in artifacts.sql.preview" :key="i"><td v-for="key in previewKeys" :key="key">{{ row[key] }}</td></tr></tbody></table></div><div v-else class="empty-state">AST 校验、EXPLAIN 和真实查询通过后显示。</div></div></div>
            <h3>动态工具执行</h3><div class="tool-grid" v-if="artifacts.data_quality?.selected_tools?.length"><article v-for="tool in artifacts.data_quality.selected_tools" :key="tool.name"><span>PASS</span><strong>{{ tool.name }}</strong><small>v{{ tool.version }}</small><p>{{ tool.reason }}</p></article></div>
          </div>

          <div v-else-if="activeTab === 'copy'" class="tab-content">
            <h3>红蓝对抗演化</h3><div class="round-list" v-if="artifacts.copy_rounds?.length"><article v-for="round in artifacts.copy_rounds" :key="round.round"><div><span>ROUND {{ round.round }}</span><strong>{{ round.score }} 分</strong></div><p>{{ round.draft }}</p><small>蓝方：{{ round.reviewer_feedback }}</small></article></div>
            <h3>A/B/C 实验资产</h3><div class="variant-grid" v-if="artifacts.copy_variants?.length"><article v-for="item in artifacts.copy_variants" :key="item.variant_id"><div class="variant-id">{{ item.variant_id }}</div><strong>{{ item.title }}</strong><p>{{ item.body }}</p><small>{{ item.strategy }} · 蓝方 {{ item.blue_score }} 分</small></article></div><div v-else class="empty-state">红蓝两轮对抗通过后生成三组可实验文案。</div>
          </div>

          <div v-else-if="activeTab === 'audit'" class="tab-content audit-layout">
            <div><h3>护栏决策</h3><div v-if="artifacts.guardrail" :class="['guard-card', guardTone]"><strong>{{ artifacts.guardrail.status }} / {{ artifacts.guardrail.risk_level }}</strong><p v-for="reason in artifacts.guardrail.reasons" :key="reason">{{ reason }}</p><ul><li v-for="(passed, key) in artifacts.guardrail.checks" :key="key"><span>{{ passed ? '✓' : '×' }}</span>{{ key }}</li></ul></div><div v-else class="empty-state">等待输入、SQL、隐私、规模和文案护栏检查。</div></div>
            <div><h3>结构化事件流</h3><div class="event-list"><article v-for="item in events" :key="item.id"><span :class="['event-dot', eventTone(item.status)]"></span><div><strong>{{ item.title }}</strong><p>{{ item.detail }}</p><small>{{ item.stage }} · {{ formatTime(item.created_at) }}</small></div></article><div v-if="!events.length" class="empty-state">暂无运行事件。</div></div><h3 class="model-heading">在线模型调用证据</h3><div class="model-calls" v-if="artifacts.model_calls?.length"><article v-for="call in artifacts.model_calls" :key="call.agent"><strong>{{ call.agent }}</strong><span>{{ call.provider }} / {{ call.model }}</span><small>{{ call.latency_ms }} ms · {{ call.output_valid ? '结构校验通过' : '失败' }}</small></article></div><div v-else class="empty-state small">离线模式不产生外部模型调用。</div></div>
          </div>

          <div v-else class="tab-content prompt-lab">
            <div class="prompt-intro"><div><p class="section-kicker">PROMPT HARNESS</p><h3>不是“凭感觉选 Prompt”，而是执行同一组黄金用例</h3><p>比较基础版、知识增强版与批判修复版在结构、SQL、引用和合规上的通过率。该离线评测真实执行 AST、DuckDB 与规则，不产生模型费用，也不冒充线上模型排行榜。</p></div><button class="primary-button" :disabled="evalRunning" @click="runEval">{{ evalRunning ? '评测中…' : '运行 Prompt 对比' }}</button></div>
            <div v-if="evalScores.length" class="eval-grid"><article v-for="score in evalScores" :key="score.prompt_version" :class="{ recommended: score.prompt_version === 'v3_critique_repair' }"><span>{{ score.prompt_version }}</span><strong>{{ score.total_score }}</strong><small>综合分 / 100</small><dl><dt>SQL执行</dt><dd>{{ percent(score.sql_pass_rate) }}</dd><dt>知识引用</dt><dd>{{ percent(score.citation_hit_rate) }}</dd><dt>文案合规</dt><dd>{{ percent(score.compliance_pass_rate) }}</dd></dl><p>{{ score.recommendation }}</p></article></div>
            <div v-else class="empty-state">点击运行后生成带评测编号、方法说明和 HTML 报告的可复现证据。</div>
            <h3 class="source-heading">知识来源清单（{{ knowledgeSources.length }}）</h3><div class="source-grid"><article v-for="source in knowledgeSources" :key="source.source_id"><span :class="['trust', source.trust_level]">{{ source.trust_level }}</span><strong>{{ source.title }}</strong><small>{{ source.publisher }} · 检索于 {{ source.retrieved_at }}</small><a v-if="source.url" :href="source.url" target="_blank" rel="noreferrer">原始来源 ↗</a></article></div>
          </div>
        </section>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const scenarios = ref([]), health = ref(null), selectedScenario = ref('churn_recall')
const authenticated = ref(false), session = ref(null), inviteCode = ref(''), authError = ref('')
const providers = ref([]), provider = ref('openai'), apiKey = ref(''), modelName = ref('')
const connectionId = ref(''), connectionMeta = ref(null), promptVersion = ref('v3_critique_repair')
const knowledgeSources = ref([]), evalScores = ref([]), evalRunning = ref(false), evalId = ref('')
const goal = ref('针对高流失、高客单价用户，设计下季度召回活动，使30天复购率相对提升5%。')
const mode = ref('offline'), runId = ref(''), snapshot = ref(null), events = ref([]), activeTab = ref('overview'), errorMessage = ref('')
let eventSource = null, lastEventId = 0
const tabs = [{ id: 'overview', label: '业务与知识' }, { id: 'data', label: 'SQL与数据' }, { id: 'copy', label: '文案与实验' }, { id: 'audit', label: '护栏与审计' }, { id: 'prompt', label: 'Prompt Lab' }]
const steps = [{ id: 'goal_planning', title: '目标解析', agent: 'GoalPlanner' }, { id: 'knowledge', title: '知识检索', agent: 'Knowledge RAG' }, { id: 'data_quality', title: '数据治理', agent: 'DataQuality' }, { id: 'sql', title: 'SQL取数', agent: 'DataAnalyst' }, { id: 'copy_adversarial', title: '红蓝对抗', agent: 'Red / Blue' }, { id: 'completed', title: '实验交付', agent: 'Experiment' }]
const artifacts = computed(() => snapshot.value?.artifacts || {})
const isRunning = computed(() => ['QUEUED', 'RUNNING'].includes(snapshot.value?.status))
const statusLabel = computed(() => ({ QUEUED: '排队中', RUNNING: '运行中', PAUSED_REVIEW: '待人工审核', COMPLETED: '已完成', BLOCKED: '已拦截', FAILED: '失败', REJECTED: '已驳回' }[snapshot.value?.status] || '尚未启动'))
const statusTone = computed(() => ({ COMPLETED: 'green', BLOCKED: 'red', FAILED: 'red', REJECTED: 'red', PAUSED_REVIEW: 'yellow', RUNNING: 'blue' }[snapshot.value?.status] || 'gray'))
const guardTone = computed(() => ({ PASS: 'guard-pass', BLOCK: 'guard-block', REVIEW: 'guard-review' }[artifacts.value.guardrail?.status] || ''))
const previewKeys = computed(() => Object.keys(artifacts.value.sql?.preview?.[0] || {}))
const briefRows = computed(() => { const b = artifacts.value.brief || {}; return { '业务目标': b.business_goal, '目标人群': b.audience_definition, '主指标': b.target_metric, '目标提升': b.target_lift ? `${Math.round(b.target_lift * 100)}%（${b.lift_type === 'relative' ? '相对' : '百分点'}）` : '—', '时间窗口': b.time_window, '触达渠道': b.channel, '假设披露': b.assumptions?.join('；') } })

function selectScenario(item) { selectedScenario.value = item.id; goal.value = item.goal; errorMessage.value = '' }
async function login() {
  authError.value = ''
  const response = await fetch('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ access_code: inviteCode.value }) })
  if (!response.ok) { authError.value = '邀请码无效或访问过于频繁'; return }
  inviteCode.value = ''; await loadSessionData()
}
async function loadSessionData() {
  const sessionRes = await fetch('/api/v1/session')
  if (!sessionRes.ok) { authenticated.value = false; return }
  session.value = await sessionRes.json(); authenticated.value = true
  const [providerRes, sourceRes] = await Promise.all([fetch('/api/v1/model-providers'), fetch('/api/v1/knowledge/sources')])
  providers.value = providerRes.ok ? (await providerRes.json()).providers : []
  knowledgeSources.value = sourceRes.ok ? (await sourceRes.json()).sources : []
}
async function connectModel() {
  errorMessage.value = ''
  const response = await fetch('/api/v1/model-connections', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: provider.value, api_key: apiKey.value, model: modelName.value || null }) })
  const data = await response.json(); apiKey.value = ''
  if (!response.ok) { errorMessage.value = data.detail || '模型连接失败'; return }
  connectionId.value = data.connection_id; connectionMeta.value = data
}
async function disconnectModel() {
  if (connectionId.value) await fetch(`/api/v1/model-connections/${connectionId.value}`, { method: 'DELETE' })
  connectionId.value = ''; connectionMeta.value = null
}
async function startRun() {
  closeStream(); events.value = []; snapshot.value = { status: 'QUEUED', artifacts: {} }; errorMessage.value = ''; lastEventId = 0
  try {
    const response = await fetch('/api/v1/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ goal: goal.value, mode: mode.value, scenario: selectedScenario.value, relative_lift: 0.05, connection_id: mode.value === 'online' ? connectionId.value : null, prompt_version: promptVersion.value }) })
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || '创建运行失败')
    runId.value = data.run_id; await refreshSnapshot(); openStream()
  } catch (error) { errorMessage.value = error.message; snapshot.value = null }
}
function openStream() {
  closeStream(); eventSource = new EventSource(`/api/v1/runs/${runId.value}/events?after=${lastEventId}`)
  eventSource.addEventListener('workflow', async event => { const item = JSON.parse(event.data); lastEventId = Math.max(lastEventId, Number(item.id || event.lastEventId || 0)); events.value.push(item); if (item.event === 'review_required' || item.event.includes('blocked')) activeTab.value = 'audit'; if (item.event === 'run_completed') activeTab.value = 'copy'; await refreshSnapshot() })
  eventSource.addEventListener('stream_end', async () => { closeStream(); await refreshSnapshot() })
  eventSource.onerror = async () => { closeStream(); await refreshSnapshot() }
}
async function refreshSnapshot() { if (!runId.value) return; const response = await fetch(`/api/v1/runs/${runId.value}`); if (response.ok) snapshot.value = await response.json() }
async function submitReview(action) { errorMessage.value = ''; const response = await fetch(`/api/v1/runs/${runId.value}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, reviewer: '课程答辩审核人', comment: action === 'approve' ? '确认仅用于合成数据灰度演示' : '覆盖规模过大，驳回任务' }) }); const data = await response.json(); if (!response.ok) { errorMessage.value = data.detail || '审核失败'; return } snapshot.value = data; openStream() }
function stepState(id) { if (!snapshot.value) return 'idle'; const seen = events.value.some(item => item.stage === id); const failed = events.value.some(item => item.stage === id && ['FAIL', 'BLOCK', 'REJECTED'].includes(item.status)); if (failed) return 'failed'; if (snapshot.value.current_stage === id && ['RUNNING', 'PAUSED_REVIEW'].includes(snapshot.value.status)) return 'active'; if (seen || snapshot.value.status === 'COMPLETED') return 'done'; return 'idle' }
function stepStateLabel(id) { return ({ idle: '等待', active: '进行中', done: '完成', failed: '拦截' }[stepState(id)]) }
function eventTone(status) { return ['BLOCK', 'FAIL', 'REJECTED'].includes(status) ? 'red' : status === 'WARN' || status === 'PAUSED' ? 'yellow' : 'green' }
function formatNumber(value) { return value === undefined || value === null ? '—' : Number(value).toLocaleString('zh-CN') }
function formatTime(value) { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '' }
function percent(value) { return `${Math.round(Number(value || 0) * 100)}%` }
async function runEval() {
  evalRunning.value = true; errorMessage.value = ''
  try {
    const response = await fetch('/api/v1/evals', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ case_limit: 10 }) })
    const data = await response.json(); if (!response.ok) throw new Error(data.detail || '评测失败')
    evalScores.value = data.scores; evalId.value = data.eval_id
  } catch (error) { errorMessage.value = error.message } finally { evalRunning.value = false }
}
function closeStream() { if (eventSource) { eventSource.close(); eventSource = null } }
onMounted(async () => {
  try {
    await loadSessionData()
    const [healthRes, scenariosRes] = await Promise.all([fetch('/health'), fetch('/api/v1/scenarios')])
    if (!healthRes.ok || !scenariosRes.ok) throw new Error('后端服务暂不可用')
    health.value = await healthRes.json()
    scenarios.value = (await scenariosRes.json()).scenarios
  } catch (error) {
    errorMessage.value = `${error.message}，请确认 FastAPI 已在 8000 端口启动。`
  }
})
onBeforeUnmount(closeStream)
</script>

<style scoped>
.login-overlay{position:fixed;inset:0;background:rgba(10,29,23,.78);backdrop-filter:blur(12px);z-index:100;display:grid;place-items:center;padding:20px}.login-card{width:min(440px,100%);background:#fff;border-radius:20px;padding:32px;box-shadow:0 28px 80px rgba(0,0,0,.3);display:flex;flex-direction:column;gap:13px}.login-card h2{margin:0;font-size:22px}.login-card p{margin:0;color:#62706a;font-size:12px;line-height:1.7}.login-card input,.connection-panel input,.connection-panel select{border:1px solid #cbd8d3;border-radius:9px;padding:10px 11px;background:#fff;color:#21312b;font-size:11px}.brand-mark.large{width:48px;height:48px;font-size:15px}.auth-error{color:#b43c31}.public-banner{background:#fff3cc;color:#725200;text-align:center;padding:7px 15px;font-size:10px;font-weight:700;border-bottom:1px solid #ead18a}.public-banner+.topbar{top:0}
.app-shell{min-height:100vh;background:#f4f7f6;color:#15211d}.topbar{height:74px;padding:0 30px;display:flex;align-items:center;justify-content:space-between;background:#fff;border-bottom:1px solid #dde5e1;position:sticky;top:0;z-index:10}.brand,.top-actions,.command-head,.command-footer,.panel-heading,.run-meta,.review-actions{display:flex;align-items:center}.brand{gap:13px}.brand-mark{width:38px;height:38px;border-radius:11px;background:#0c6b52;color:#fff;display:grid;place-items:center;font-weight:800;font-size:13px;letter-spacing:.5px}.eyebrow,.section-kicker{margin:0 0 3px;color:#6e7e77;font-size:10px;font-weight:800;letter-spacing:1.5px}.brand h1{font-size:17px;margin:0;letter-spacing:-.2px}.top-actions{gap:10px}.status-pill,.mode-pill,.count-chip{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:7px 10px;font-size:11px;font-weight:700;background:#edf1ef;color:#52615b}.status-pill.green{background:#e7f7f0;color:#087354}.status-pill.blue{background:#e8f1fb;color:#2465a6}.status-pill.yellow{background:#fff5d9;color:#8d6200}.status-pill.red{background:#fde9e7;color:#a4392d}.dot{width:6px;height:6px;border-radius:50%;background:currentColor}.mode-pill{background:#eef0ff;color:#5552a3}.text-button{color:#0c6b52;text-decoration:none;font-size:12px;font-weight:700;padding:8px 11px;border:1px solid #cbd9d3;border-radius:8px}.workspace{display:grid;grid-template-columns:270px minmax(0,1fr);gap:18px;padding:18px 26px 30px;max-width:1600px;margin:auto}.panel{background:#fff;border:1px solid #dde5e1;border-radius:15px;box-shadow:0 2px 10px rgba(20,45,36,.035)}.scenario-panel{padding:18px;height:calc(100vh - 112px);position:sticky;top:92px;display:flex;flex-direction:column}.panel-heading{justify-content:space-between;margin-bottom:15px}.panel-heading h2,.command-head h2{font-size:15px;margin:0}.count-chip{padding:5px 9px}.scenario-list{display:flex;flex-direction:column;gap:7px;overflow:auto}.scenario-card{appearance:none;border:1px solid transparent;background:#f6f8f7;border-radius:10px;display:flex;align-items:center;padding:11px 10px;text-align:left;cursor:pointer;color:#33413b}.scenario-card:hover{border-color:#c7d9d2}.scenario-card.active{background:#e9f5f0;border-color:#7db8a5}.risk-dot{width:8px;height:8px;border-radius:50%;margin-right:10px;flex:0 0 auto}.risk-dot.green{background:#19a974}.risk-dot.yellow{background:#e4a72b}.risk-dot.red{background:#d44b3e}.scenario-copy{display:flex;flex-direction:column;gap:4px;min-width:0}.scenario-copy strong{font-size:12px}.scenario-copy small{font-size:9px;color:#7c8984;letter-spacing:.8px}.chevron{margin-left:auto;color:#92a09a;font-size:18px}.infra-card{margin-top:auto;background:#132a23;color:#fff;border-radius:12px;padding:14px}.infra-card>p{font-size:11px;color:#9fbab0;margin:0 0 10px}.infra-card>div{display:flex;align-items:baseline;justify-content:space-between;border-top:1px solid rgba(255,255,255,.09);padding:7px 0}.infra-card strong{font-size:14px}.infra-card span,.infra-card small{font-size:9px;color:#9fbab0}.main-column{display:flex;flex-direction:column;gap:14px;min-width:0}.command-panel,.workflow-panel,.evidence-panel{padding:18px 20px}.command-head{justify-content:space-between}.mode-switch{display:flex;background:#eef2f0;padding:3px;border-radius:9px}.mode-switch button{border:0;background:transparent;padding:6px 12px;border-radius:7px;font-size:11px;color:#68766f;cursor:pointer}.mode-switch button.active{background:#fff;color:#0c6b52;box-shadow:0 1px 4px rgba(0,0,0,.08);font-weight:700}.command-panel textarea{width:100%;box-sizing:border-box;margin-top:13px;border:1px solid #ced9d4;border-radius:10px;padding:13px 14px;resize:vertical;color:#20302a;font:13px/1.65 inherit;outline:none}.command-panel textarea:focus{border-color:#4b9d82;box-shadow:0 0 0 3px #e1f2ec}.command-footer{justify-content:space-between;margin-top:10px}.assumption{font-size:10px;color:#6f7d77}.assumption span{color:#9a6d08;background:#fff5d8;border-radius:5px;padding:3px 6px;margin-right:6px;font-weight:700}.primary-button,.approve-button,.reject-button{border:0;border-radius:9px;padding:10px 16px;font-weight:700;font-size:12px;cursor:pointer}.primary-button,.approve-button{background:#0c6b52;color:#fff}.primary-button:disabled{opacity:.55;cursor:not-allowed}.reject-button{background:#fff;color:#a4392d;border:1px solid #e8b9b3}.spinner{display:inline-block;width:10px;height:10px;border:2px solid rgba(255,255,255,.45);border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite;margin-right:6px}.error-banner{background:#fdebea;color:#a23c31;padding:9px 12px;border-radius:8px;font-size:11px}.panel-heading.compact{margin-bottom:12px}.run-meta{gap:8px}.run-meta code{font-size:10px;color:#79857f}.step-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}.step-card{border:1px solid #e2e8e5;background:#fafbfa;border-radius:10px;padding:10px;min-width:0;position:relative}.step-card.active{border-color:#56a88d;background:#eff9f5}.step-card.done{border-color:#b8dccf;background:#f4fbf8}.step-card.failed{border-color:#e8aaa3;background:#fff6f5}.step-index{font:700 9px/1 monospace;color:#99a59f}.step-card>div{margin-top:7px;display:flex;flex-direction:column}.step-card strong{font-size:11px}.step-card small{font-size:9px;color:#7b8983;margin-top:3px}.step-state{position:absolute;right:8px;top:8px;font-size:8px;color:#89958f}.step-card.active .step-state{color:#0c6b52}.step-card.failed .step-state{color:#b4372b}.metrics-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.metric-card{padding:14px 16px;display:flex;flex-direction:column}.metric-card span{font-size:10px;color:#738079}.metric-card strong{font-size:23px;margin:5px 0 2px;letter-spacing:-.5px}.metric-card small{font-size:9px;color:#97a19d}.guard-pass{color:#087354}.guard-block{color:#b33c30}.guard-review{color:#9a6c00}.review-banner{background:#fff7e4;border:1px solid #ecd394;border-radius:14px;padding:17px 19px;display:flex;align-items:center;justify-content:space-between}.review-banner h3{margin:2px 0 5px;font-size:15px}.review-banner p{margin:0;color:#756242;font-size:11px}.review-actions{gap:8px}.tabbar{display:flex;border-bottom:1px solid #e2e8e5;gap:20px}.tabbar button{border:0;background:transparent;padding:0 2px 12px;color:#78847e;font-size:11px;font-weight:700;cursor:pointer;border-bottom:2px solid transparent}.tabbar button.active{color:#0c6b52;border-color:#0c6b52}.tab-content{padding-top:17px}.tab-content h3{font-size:12px;margin:0 0 10px}.two-column,.audit-layout,.subgrid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.definition-list{margin:0;display:grid;grid-template-columns:82px 1fr;border-top:1px solid #e7ece9}.definition-list dt,.definition-list dd{padding:8px 0;margin:0;border-bottom:1px solid #e7ece9;font-size:10px}.definition-list dt{color:#78847e}.definition-list dd{color:#26352f}.citation-list{display:flex;flex-direction:column;gap:8px}.citation-list article{border:1px solid #e1e8e5;border-radius:9px;padding:9px 10px}.citation-list code{font-size:8px;background:#edf4f1;color:#0c6b52;padding:3px 5px;border-radius:4px;margin-right:7px}.citation-list strong{font-size:10px}.citation-list p{font-size:9px;line-height:1.5;color:#6e7a75;margin:5px 0 0}.empty-state{min-height:100px;background:#f7f9f8;border:1px dashed #d6dfdb;border-radius:9px;display:grid;place-items:center;text-align:center;padding:15px;color:#87928d;font-size:10px}.code-block{height:270px;margin:0;overflow:auto;background:#10241d;color:#cde9df;border-radius:10px;padding:13px;font:9.5px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap}.table-wrap{height:296px;overflow:auto;border:1px solid #e0e7e4;border-radius:9px}table{border-collapse:collapse;width:100%;font-size:9px}th{position:sticky;top:0;background:#edf4f1;color:#51645c;text-align:left}th,td{padding:8px;border-bottom:1px solid #e5ebe8;white-space:nowrap}.tool-grid,.variant-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.tool-grid article,.variant-grid article,.round-list article{border:1px solid #e1e8e5;border-radius:9px;padding:10px}.tool-grid article>span{font-size:8px;color:#087354;background:#e5f7ef;padding:3px 5px;border-radius:4px}.tool-grid strong{font-size:9px;display:block;margin-top:8px}.tool-grid small{font-size:8px;color:#89948f}.tool-grid p{font-size:8px;color:#69766f;line-height:1.45}.round-list{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-bottom:18px}.round-list article>div{display:flex;justify-content:space-between;font-size:9px}.round-list article p{font-size:10px;line-height:1.55}.round-list article small{color:#7c8983;font-size:9px}.variant-grid{grid-template-columns:repeat(3,1fr)}.variant-grid article{position:relative;padding:13px}.variant-id{position:absolute;right:10px;top:10px;background:#102c23;color:#fff;width:22px;height:22px;border-radius:7px;display:grid;place-items:center;font-weight:800;font-size:10px}.variant-grid strong{font-size:11px}.variant-grid p{font-size:10px;line-height:1.6;min-height:48px;margin-right:18px}.variant-grid small{font-size:8px;color:#77847e}.guard-card{border-radius:10px;padding:14px;background:#f4f8f6;border:1px solid #dbe6e1}.guard-card.guard-block{background:#fff5f4;border-color:#edc0bb}.guard-card.guard-review{background:#fff9ea;border-color:#ead79e}.guard-card>strong{font-size:18px}.guard-card p{font-size:10px}.guard-card ul{list-style:none;padding:0;margin:10px 0 0;display:grid;grid-template-columns:1fr 1fr;gap:6px}.guard-card li{font-size:9px}.guard-card li span{display:inline-grid;place-items:center;width:15px;height:15px;border-radius:50%;background:#e3f4ed;color:#087354;margin-right:5px}.event-list{max-height:360px;overflow:auto}.event-list article{display:flex;gap:9px;padding:7px 0;border-bottom:1px solid #edf1ef}.event-dot{width:7px;height:7px;border-radius:50%;margin-top:4px;flex:0 0 auto}.event-dot.green{background:#1b9b70}.event-dot.yellow{background:#d89c24}.event-dot.red{background:#d34b3f}.event-list strong{font-size:9px}.event-list p{font-size:9px;color:#63716b;margin:2px 0}.event-list small{font-size:8px;color:#9aa49f}@keyframes spin{to{transform:rotate(360deg)}}
.connection-panel{margin-top:10px;padding:11px;background:#f3f5ff;border:1px solid #d9ddf4;border-radius:11px;display:grid;grid-template-columns:minmax(210px,1.6fr) 150px 180px 210px auto;gap:8px;align-items:center}.connection-copy{display:flex;flex-direction:column;gap:4px}.connection-copy strong{font-size:11px;color:#393875}.connection-copy small{font-size:8px;line-height:1.4;color:#727197}.outline-button,.connected-button{border:1px solid #7c7ab4;background:#fff;color:#4c4a91;border-radius:8px;padding:9px;font-size:10px;font-weight:700;cursor:pointer}.connected-button{background:#e5f7ef;border-color:#83bba8;color:#087354}.citation-list em{display:block;margin-top:5px;font-style:normal;font-size:8px;color:#839089}.citation-list a,.source-grid a{display:inline-block;margin-top:5px;color:#0c6b52;text-decoration:none;font-size:8px}.model-heading,.source-heading{margin-top:18px!important}.model-calls{display:grid;grid-template-columns:1fr 1fr;gap:7px}.model-calls article{border:1px solid #e1e8e5;border-radius:8px;padding:8px;display:flex;flex-direction:column}.model-calls strong{font-size:9px}.model-calls span,.model-calls small{font-size:8px;color:#718078}.empty-state.small{min-height:55px}.prompt-intro{display:flex;justify-content:space-between;gap:20px;align-items:center;background:#f3f5ff;border-radius:12px;padding:15px}.prompt-intro h3{font-size:14px}.prompt-intro p{max-width:760px;color:#68716f;font-size:10px;line-height:1.6;margin:5px 0 0}.eval-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.eval-grid article{border:1px solid #dde5e1;border-radius:11px;padding:14px;display:flex;flex-direction:column}.eval-grid article.recommended{border-color:#42a383;background:#f0faf6}.eval-grid article>span{font:700 9px ui-monospace;color:#66736d}.eval-grid article>strong{font-size:29px;margin-top:8px}.eval-grid article>small{font-size:8px;color:#8a9690}.eval-grid dl{display:grid;grid-template-columns:1fr auto;gap:5px;font-size:9px;border-top:1px solid #e0e7e4;padding-top:9px}.eval-grid dt{color:#718078}.eval-grid dd{margin:0;font-weight:700}.eval-grid p{font-size:9px;line-height:1.5;color:#5f6c66}.source-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.source-grid article{border:1px solid #e1e8e5;border-radius:9px;padding:10px;display:flex;flex-direction:column;gap:5px}.source-grid strong{font-size:9px;line-height:1.4}.source-grid small{font-size:8px;color:#7d8983}.trust{align-self:flex-start;font-size:7px;text-transform:uppercase;padding:3px 5px;border-radius:4px;background:#eef1f0}.trust.official{background:#e7f7f0;color:#087354}.trust.internal{background:#eef0ff;color:#5552a3}
@media(max-width:1200px){.connection-panel{grid-template-columns:1fr 1fr}.connection-copy{grid-column:1/-1}.source-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:1050px){.workspace{grid-template-columns:1fr}.scenario-panel{position:static;height:auto}.scenario-list{display:grid;grid-template-columns:repeat(3,1fr)}.infra-card{display:none}.step-grid{grid-template-columns:repeat(3,1fr)}.tool-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:720px){.topbar{padding:0 14px}.top-actions .mode-pill,.run-meta code{display:none}.workspace{padding:12px}.scenario-list,.metrics-grid,.two-column,.audit-layout,.subgrid,.variant-grid,.round-list,.eval-grid,.source-grid,.connection-panel{grid-template-columns:1fr}.step-grid{grid-template-columns:repeat(2,1fr)}.command-footer,.review-banner,.prompt-intro{align-items:flex-start;gap:12px;flex-direction:column}.tool-grid{grid-template-columns:1fr 1fr}.tabbar{overflow-x:auto}.tabbar button{white-space:nowrap}}
</style>
