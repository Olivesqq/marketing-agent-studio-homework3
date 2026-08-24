from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import router
from app.core.config import settings
from app.services.database import AnalyticsDatabase
from app.services.knowledge import KnowledgeService
from app.services.state_store import StateStore
from app.services.tool_registry import registry
from app.services.workflow import WorkflowEngine
from app.services.security import ModelKeyVault, SessionManager, SlidingWindowRateLimiter
from app.services.eval_harness import PromptEvalHarness


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.PUBLIC_DEMO:
        insecure = []
        if not settings.REQUIRE_INVITE_CODE:
            insecure.append("REQUIRE_INVITE_CODE")
        if settings.APP_SIGNING_KEY == "local-development-signing-key-change-me":
            insecure.append("APP_SIGNING_KEY")
        if not settings.SESSION_COOKIE_SECURE:
            insecure.append("SESSION_COOKIE_SECURE")
        if insecure:
            raise RuntimeError(f"公开演示拒绝以不安全配置启动：{', '.join(insecure)}")
    database = AnalyticsDatabase(settings.ANALYTICS_DB, settings.DATA_SEED)
    database.initialize()
    store = StateStore(settings.STATE_DB)
    knowledge = KnowledgeService(settings.KNOWLEDGE_DIR)
    sessions = SessionManager(settings)
    vault = ModelKeyVault(settings)
    app.state.database = database
    app.state.store = store
    app.state.knowledge = knowledge
    app.state.tools = registry
    app.state.sessions = sessions
    app.state.vault = vault
    app.state.rate_limiter = SlidingWindowRateLimiter(settings.RATE_LIMIT_PER_MINUTE)
    app.state.eval_harness = PromptEvalHarness(database, knowledge)
    app.state.engine = WorkflowEngine(settings, store, database, knowledge, registry, vault)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="可复现、可审计的电商营销多智能体协同系统",
    version="3.0.0",
    lifespan=lifespan,
    docs_url=None if settings.PUBLIC_DEMO else "/docs",
    redoc_url=None if settings.PUBLIC_DEMO else "/redoc",
    openapi_url=None if settings.PUBLIC_DEMO else "/openapi.json",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.PUBLIC_ORIGIN, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)


@app.middleware("http")
async def public_security(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_REQUEST_BYTES:
        return JSONResponse(status_code=413, content={"detail": "请求体过大"})
    if request.url.path.startswith("/api/"):
        identity = request.client.host if request.client else "unknown"
        token = request.cookies.get(settings.SESSION_COOKIE_NAME)
        sid = getattr(request.app.state, "sessions", None)
        if sid:
            identity = sid.verify(token) or identity
        limiter = getattr(request.app.state, "rate_limiter", None)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and limiter and not limiter.allow(identity):
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试"})
        if settings.PUBLIC_DEMO and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if origin and origin != settings.PUBLIC_ORIGIN:
                return JSONResponse(status_code=403, content={"detail": "跨站请求已拒绝"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if settings.SESSION_COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(router)


@app.get("/health")
async def health():
    database = app.state.database
    return {
        "status": "UP",
        "project": settings.PROJECT_NAME,
        "default_mode": settings.APP_MODE,
        "online_ready": True,
        "analytics": {"engine": "DuckDB", "fingerprint": database.fingerprint(), "tables": database.table_counts()},
        "workflow_state": {"engine": "SQLite", "path": settings.STATE_DB.name},
        "knowledge_documents": app.state.knowledge.document_count,
        "registered_tools": len(app.state.tools.manifest()),
    }


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")
    candidate = (FRONTEND_DIST / path).resolve()
    if path and FRONTEND_DIST.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="前端尚未构建")
