# 公开演示安全说明

本项目只处理固定随机种子生成的合成电商数据，不接入真实用户、真实支付、真实投放或生产数据库。公开环境启用邀请码、签名 HttpOnly Cookie、SameSite=Strict、精确 CORS、Origin 校验、会话级运行隔离、限流、并发上限、安全响应头和 DLP 输入拦截。

## 自带密钥（BYOK）边界

- API Key 只进入服务进程内存，使用随机 `connection_id` 引用，默认 30 分钟过期。
- Key 不进入 SQLite、DuckDB、工作流事件、导出文件、浏览器 localStorage/sessionStorage 或应用日志。
- 仅允许 OpenAI、DashScope 与 DeepSeek 三个固定官方地址，用户不能填写任意 Base URL，从而降低 SSRF 风险。
- 公开服务不配置共享模型密钥；免费 Render 实例重启后，内存 Key 与运行中状态会失效。

## 禁止提交的数据

真实姓名、手机号、邮箱、身份证、银行卡、账号密码、生产 API Key、Cookie、真实订单或内部经营数据均不应提交。DLP 会拦截常见格式，但自动检测不是用户提交敏感数据的授权。

## 生产部署前检查

1. 将 `APP_SIGNING_KEY` 设置为平台生成的高熵 Secret。
2. 设置至少 12 位随机 `DEMO_ACCESS_CODE`，或使用 `scripts/hash_access_code.py` 生成哈希。
3. 将 `PUBLIC_ORIGIN` 和 `ALLOWED_HOSTS` 精确设置为最终域名。
4. 保持 `PUBLIC_DEMO=true`、`REQUIRE_INVITE_CODE=true`、`SESSION_COOKIE_SECURE=true`。
5. 运行后端测试、`npm audit --omit=dev`、秘密扫描及浏览器越权检查。

安全问题请不要在公开 Issue 中包含密钥或真实数据；应先撤销受影响的 Key，再通过私密渠道报告。
