from __future__ import annotations

import json
import asyncio
import os
import re
import secrets
import shutil
import base64
import hashlib
import hmac
import time
import zipfile
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from libshared import artifacts, checkpoint
from libshared.local_env import load_local_env
from libshared.paths import DATA_ROOT, ROOT, RUNS_ROOT
from orchestrator import cost_tracker, engine, queue, user_store
from orchestrator.capabilities import capability_map
from tools import tool_registry
from tools.collect import manual_import, product_library, tiktok_oembed


load_local_env()


WEB_ROOT = ROOT / "web"
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,96}$")
ARTIFACT_NAMES = {
    "analysis_report",
    "script_copy",
    "review_report",
    "shot_plan",
    "asset_manifest",
    "shot_report",
    "render_report",
    "qa_report",
    "publish_archive",
    "research_brief",
    "strategy_brief",
    "script_breakdown",
    "take_manifest",
    "feedback_record",
}
GATE_STAGES = ("script_gate", "hero_gate", "take_gate")
NODE_STAGES = {
    "collector": (),
    "analysis": ("analysis", "research"),
    "script": ("strategy", "script", "script_breakdown"),
    "storyboard": ("storyboard",),
    "asset": ("asset", "hero_gate"),
    "media": ("production", "take_gate", "compose"),
    "review": ("script_review", "script_gate", "final_qa", "archive"),
}
STATUS_PRIORITY = (
    "failed",
    "blocked",
    "needs_review",
    "awaiting_human",
    "running",
    "queued",
    "succeeded",
    "idle",
)
LOGIN_FAILURES: dict[str, deque[float]] = defaultdict(deque)
REGISTRATION_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
LOGIN_WINDOW_S = 60
LOGIN_FAILURE_LIMIT = 5
REGISTRATION_WINDOW_S = 3600
REGISTRATION_LIMIT = 5
PENDING_REGISTRATION_LIMIT = 200


class PipelineRunRequest(BaseModel):
    project_id: str | None = None
    product_id: str = "便携恒温杯"
    source_link_id: int | None = None
    source_material_id: str | None = None
    source_text: str | None = None
    link_id: str | int | None = None
    mock: bool = True


class ManualCollectRequest(BaseModel):
    links_text: str = ""
    urls: list[str] | None = None
    items: list[dict[str, Any]] | None = None
    product_id: str = "便携恒温杯"
    source_keyword: str = "manual_tiktok"


class TikTokCollectRequest(ManualCollectRequest):
    source_keyword: str = "tiktok_oembed"


class TikTokIntakeRunRequest(BaseModel):
    url: str
    product_id: str = "便携恒温杯"
    transcript_text: str | None = None
    source_item: dict[str, Any] | None = None
    project_id: str | None = None
    mock: bool = True


class TikTokCrawlRequest(BaseModel):
    target_type: str = "keyword"
    provider: str = "auto"
    target: str
    limit: int = 6
    product_id: str = "便携恒温杯"
    mock: bool = True


class AutoCollectorSettingsRequest(BaseModel):
    enabled: bool = False
    target_type: str = "keyword"
    provider: str = "auto"
    target: str = ""
    limit: int = 3
    interval_minutes: int = 60
    product_id: str = "便携恒温杯"
    mock: bool = True


class ProductLibraryRefreshRequest(BaseModel):
    source_roots: list[str] | None = None


class GateApproveRequest(BaseModel):
    project_id: str
    stage: str
    approver: str = "operator"
    notes: str | None = None
    mock: bool = True


class GateRewriteRequest(BaseModel):
    project_id: str
    stage: str = "script_gate"
    reason: str | None = None
    mock: bool = True


class HeroRegenRequest(BaseModel):
    project_id: str
    shot_index: int


class TaskRetryRequest(BaseModel):
    project_id: str
    task_id: int | None = None
    shot_index: int | None = None
    mock: bool = True


class ManualStageRunRequest(BaseModel):
    project_id: str
    stage: str
    shot_index: int | None = None
    take_id: str | None = None
    mock: bool = True


class TakeSelectRequest(BaseModel):
    project_id: str
    shot_index: int
    take_id: str


class TakeReviewRequest(BaseModel):
    project_id: str
    shot_index: int
    take_id: str
    product_identity: bool = False
    no_invented_brand: bool = False
    temperature_display: bool = False
    usage_flow: bool = False
    continuity: bool = False
    notes: str = ""


class FeedbackRequest(BaseModel):
    project_id: str
    text: str
    author: str = "operator"


class FinalVisualReviewRequest(BaseModel):
    project_id: str
    product_identity: bool
    no_invented_brand: bool
    temperature_display: bool
    usage_flow: bool
    person_scene_continuity: bool
    reviewer: str = "operator"
    notes: str | None = None


class AgentRunRequest(BaseModel):
    project_id: str | None = None
    action: str
    source_text: str | None = None
    source_refs: list[str] | None = None
    product_id: str = "便携恒温杯"
    prompt: str | None = None
    input_json: dict[str, Any] | None = None
    target_type: str = "keyword"
    target: str | None = None
    provider: str = "auto"
    limit: int = 6
    persist: bool = True
    mock: bool = True


class StandalonePromoteRequest(BaseModel):
    source_project_id: str
    artifact_name: str
    project_id: str | None = None
    product_id: str | None = None
    mock: bool = True


class LoginRequest(BaseModel):
    username: str
    password: str = ""
    portal: str = "operator"


class RegistrationRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""


class RegistrationReviewRequest(BaseModel):
    note: str = ""


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "operator"
    display_name: str = ""


class UserUpdateRequest(BaseModel):
    status: str | None = None
    password: str | None = None
    display_name: str | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    queue.init_db(db_path=_db_path())
    if _auth_enabled():
        user_store.seed_environment_users(db_path=_db_path())
    queue.recover_running_tasks_on_startup(db_path=_db_path())
    _ensure_auto_collector_settings()
    _recover_auto_collector_on_startup()
    scheduler = asyncio.create_task(_auto_collector_loop())
    try:
        yield
    finally:
        scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass


app = FastAPI(title="video-agent-factory", version="0.0.0", lifespan=lifespan)
if WEB_ROOT.exists():
    app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if _auth_enabled() and request.url.path.startswith(("/api/v2/", "/workbench", "/admin")):
        if request.url.path.startswith("/api/v2/auth/"):
            return await call_next(request)
        session = _read_session(request)
        if session is None:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "authentication required"}, status_code=401)
            return RedirectResponse("/login", status_code=303)
        if request.url.path.startswith(("/admin", "/api/v2/admin")) and session.get("role") != "admin":
            return JSONResponse({"detail": "administrator role required"}, status_code=403)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


@app.get("/login", include_in_schema=False)
def login_page() -> FileResponse:
    return FileResponse(WEB_ROOT / "login.html", headers={"Cache-Control": "no-store"})


@app.get("/workbench", include_in_schema=False)
def workbench() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/admin", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(WEB_ROOT / "admin.html", headers={"Cache-Control": "no-store"})


@app.post("/api/v2/auth/login")
def login(request: LoginRequest, raw_request: Request) -> JSONResponse:
    role = request.portal.strip().casefold()
    if role not in {"operator", "admin"}:
        raise HTTPException(status_code=400, detail="unknown portal")
    username = request.username.strip()
    client_ip = _client_ip(raw_request)
    login_key = f"{client_ip}:{username.casefold()}"
    if _rate_limited(LOGIN_FAILURES, login_key, LOGIN_WINDOW_S, LOGIN_FAILURE_LIMIT):
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后再试")
    authenticated_role = role
    if _auth_enabled():
        configuration_error = _auth_configuration_error()
        if configuration_error:
            raise HTTPException(status_code=503, detail=configuration_error)
        account = user_store.authenticate(username, request.password, db_path=_db_path())
        if account is None:
            _record_attempt(LOGIN_FAILURES, login_key, LOGIN_WINDOW_S)
            raise HTTPException(status_code=401, detail="账号或密码错误")
        LOGIN_FAILURES.pop(login_key, None)
        authenticated_role = str(account["role"])
        if role == "admin" and authenticated_role != "admin":
            raise HTTPException(status_code=403, detail="该账号没有管理员权限")
    elif not username:
        username = "local-admin" if role == "admin" else "local-operator"
    response = JSONResponse({"ok": True, "role": authenticated_role, "username": username, "redirect": "/admin" if role == "admin" else "/workbench"})
    response.set_cookie(
        "vaf_session",
        _sign_session(username, authenticated_role),
        httponly=True,
        secure=_env_bool("VAF_COOKIE_SECURE", _auth_enabled()),
        samesite="strict",
        max_age=8 * 60 * 60,
    )
    return response


@app.post("/api/v2/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie("vaf_session")
    return response


@app.post("/api/v2/auth/register")
def register_account(request: RegistrationRequest, raw_request: Request) -> dict[str, Any]:
    if not _auth_enabled():
        raise HTTPException(status_code=409, detail="registration is only available when intranet authentication is enabled")
    if not _self_registration_enabled():
        raise HTTPException(status_code=403, detail="self registration is disabled; contact an administrator")
    client_ip = _client_ip(raw_request)
    if _rate_limited(REGISTRATION_ATTEMPTS, client_ip, REGISTRATION_WINDOW_S, REGISTRATION_LIMIT):
        raise HTTPException(status_code=429, detail="注册申请过于频繁，请一小时后再试")
    if user_store.pending_registration_count(db_path=_db_path()) >= PENDING_REGISTRATION_LIMIT:
        raise HTTPException(status_code=429, detail="待审核注册申请已达上限，请联系管理员")
    try:
        registration = user_store.request_registration(
            request.username,
            request.password,
            display_name=request.display_name,
            db_path=_db_path(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _record_attempt(REGISTRATION_ATTEMPTS, client_ip, REGISTRATION_WINDOW_S)
    return {"ok": True, "registration": registration}


@app.get("/api/v2/auth/session")
def auth_session(request: Request) -> dict[str, Any]:
    session = _read_session(request)
    return {"authenticated": session is not None, "auth_enabled": _auth_enabled(), **(session or {})}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    queue.init_db(db_path=_db_path())
    return {"status": "ok"}


@app.get("/api/v2/runtime")
def runtime_status() -> dict[str, Any]:
    from tools.collect import tiktok_api_adapter

    tiktok_api_installed = tiktok_api_adapter.package_available()
    tiktok_api_ready = tiktok_api_adapter.configured(os.environ)
    apify_ready = bool(os.environ.get("APIFY_API_TOKEN"))
    yt_dlp_ready = bool(shutil.which("yt-dlp"))
    cookies_ready = bool(os.environ.get("TIKTOK_COOKIES_FILE"))
    return {
        "status": "ok",
        "real_ready": bool(os.environ.get("DOUBAO_API_KEY") and os.environ.get("SEEDANCE_API_KEY")),
        "providers": {
            "doubao": {"configured": bool(os.environ.get("DOUBAO_API_KEY"))},
            "seedance": {"configured": bool(os.environ.get("SEEDANCE_API_KEY"))},
            "tiktok_oembed": {"configured": True},
            "tiktok_video": {"configured": bool(shutil.which("yt-dlp"))},
            "tiktok_keyword_crawler": {
                "configured": apify_ready or tiktok_api_ready,
                "mode": "tiktok_api_or_apify",
            },
            "tiktok_api": {
                "configured": tiktok_api_ready,
                "installed": tiktok_api_installed,
                "mode": "account_hashtag_trending",
            },
            "speech_to_text": {"configured": False, "mode": "subtitle_or_operator_text"},
        },
        "collector_backends": [
            {"id": "tiktok_api", "ready": tiktok_api_ready, "supports": ["account", "hashtag", "keyword", "trending"]},
            {"id": "apify", "ready": apify_ready, "supports": ["keyword"]},
            {"id": "yt_dlp", "ready": yt_dlp_ready, "supports": ["account", "direct_url"], "cookies_file": cookies_ready},
            {"id": "manual_url", "ready": yt_dlp_ready, "supports": ["direct_url"]},
        ],
        "budget_mode": "observe",
        "pricing_calibrated": False,
    }


@app.get("/api/v2/agents")
def agent_capabilities() -> dict[str, Any]:
    return capability_map()


@app.get("/api/v2/admin/summary")
def admin_summary() -> dict[str, Any]:
    queue.init_db(db_path=_db_path())
    with queue.get_conn(_db_path()) as conn:
        project_rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        task_rows = conn.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall()
        total_cost = float(conn.execute("SELECT COALESCE(SUM(cost_cny), 0) FROM cost_entries").fetchone()[0])
        failures = [
            dict(row)
            for row in conn.execute(
                "SELECT project_id, stage, agent, error_json, updated_at FROM tasks WHERE status = 'failed' ORDER BY updated_at DESC LIMIT 12"
            ).fetchall()
        ]
    material_index = manual_import.load_library_index(_material_library_root())
    runs_root = _runs_root()
    users = user_store.list_users(db_path=_db_path())
    summaries = [_project_summary(str(row["id"]), row=row) for row in project_rows]
    project_counts: dict[str, int] = {}
    for summary in summaries:
        project_counts[summary["status"]] = project_counts.get(summary["status"], 0) + 1
    recent = [
        {
            "id": summary["project_id"],
            "product_id": summary["product_id"],
            "status": summary["status"],
            "current_stage": summary["current_stage"],
            "created_at": summary["created_at"],
            "updated_at": summary["updated_at"],
        }
        for summary in summaries[:12]
    ]
    return {
        "status": "ok",
        "projects": project_counts,
        "tasks": {row["status"]: row["count"] for row in task_rows},
        "total_cost_cny": round(total_cost, 4),
        "material_count": len(material_index.get("items") or []),
        "run_count": len([path for path in runs_root.iterdir() if path.is_dir()]) if runs_root.exists() else 0,
        "storage_bytes": {
            "database": _path_size(queue.resolve_db_path(_db_path())),
            "materials": _path_size(_material_library_root()),
            "runs": _path_size(runs_root),
        },
        "recent_projects": recent,
        "recent_failures": failures,
        "runtime": runtime_status(),
        "users": {
            "total": len(users),
            "active": len([user for user in users if user["status"] == "active"]),
        },
    }


@app.get("/api/v2/admin/users")
def admin_users() -> dict[str, Any]:
    return {"items": user_store.list_users(db_path=_db_path())}


@app.post("/api/v2/admin/users")
def create_admin_user(request: UserCreateRequest) -> dict[str, Any]:
    try:
        user = user_store.create_user(
            request.username,
            request.password,
            role=request.role,
            display_name=request.display_name,
            db_path=_db_path(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "user": user}


@app.patch("/api/v2/admin/users/{user_id}")
def update_admin_user(user_id: int, request: UserUpdateRequest) -> dict[str, Any]:
    try:
        user = user_store.update_user(
            user_id,
            status=request.status,
            password=request.password,
            display_name=request.display_name,
            db_path=_db_path(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="user not found") from exc
    return {"ok": True, "user": user}


@app.get("/api/v2/admin/registration-requests")
def admin_registration_requests() -> dict[str, Any]:
    return {"items": user_store.list_registration_requests(db_path=_db_path())}


@app.post("/api/v2/admin/registration-requests/{request_id}/approve")
def approve_registration_request(request_id: int, request: RegistrationReviewRequest, raw_request: Request) -> dict[str, Any]:
    session = _read_session(raw_request) or {}
    try:
        item = user_store.review_registration_request(
            request_id,
            approve=True,
            reviewer=str(session.get("username") or "admin"),
            note=request.note,
            db_path=_db_path(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="registration request not found") from exc
    return {"ok": True, "registration": item}


@app.post("/api/v2/admin/registration-requests/{request_id}/reject")
def reject_registration_request(request_id: int, request: RegistrationReviewRequest, raw_request: Request) -> dict[str, Any]:
    session = _read_session(raw_request) or {}
    try:
        item = user_store.review_registration_request(
            request_id,
            approve=False,
            reviewer=str(session.get("username") or "admin"),
            note=request.note,
            db_path=_db_path(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="registration request not found") from exc
    return {"ok": True, "registration": item}


@app.post("/api/v2/agents/run")
def run_agent_capability(request: AgentRunRequest) -> dict[str, Any]:
    standalone = not request.project_id
    action = request.action.strip().casefold()
    project_id = _validate_project_id(request.project_id or _new_standalone_id())
    if standalone and action != "collector":
        queue.ensure_project(
            project_id,
            product_id=request.product_id,
            payload={"standalone": True, "standalone_action": action},
            db_path=_db_path(),
        )
    project = _project_summary(project_id) if action != "collector" else {}
    root = _run_root(project_id)
    payload: dict[str, Any] = {"project_id": project_id}

    if action == "collector":
        if not request.target:
            raise HTTPException(status_code=400, detail="collector requires target")
        if request.persist:
            captured = crawl_tiktok_and_run(
                TikTokCrawlRequest(
                    target_type=request.target_type,
                    provider=request.provider,
                    target=request.target,
                    limit=max(1, min(request.limit, 20)),
                    product_id=request.product_id,
                    mock=request.mock,
                )
            )
            return {
                "ok": captured["ok"],
                "project_id": None,
                "action": action,
                "artifact_name": "tiktok_capture",
                "artifact": captured,
                "meta": {"persisted": True, "provider": captured.get("provider")},
            }
        result = tool_registry.execute_tool(
            "tiktok_crawler",
            {"target_type": request.target_type, "target": request.target, "provider": request.provider, "limit": max(1, min(request.limit, 20))},
            context={"mock": request.mock, "env": os.environ},
        )
        if not result.ok:
            raise HTTPException(status_code=422, detail=(result.error or {}).get("message") or result.error)
        return {"ok": True, "project_id": project_id if not standalone else None, "action": action, "artifact_name": "tiktok_discovery", "artifact": result.data, "meta": result.meta}
    if action == "analysis":
        source = (request.source_text or request.prompt or "").strip()
        payload.update(
            {
                "transcript_text": source,
                "source_material_id": (request.source_refs or [None])[0],
                "source_url": source if source.startswith(("http://", "https://")) else "",
            }
        )
        tool_name, artifact_name = "doubao_analyze", "analysis_report"
    elif action == "research":
        analysis = _load_artifact_or_none(project_id, "analysis_report") or {}
        payload.update(
            {
                "source_text": request.source_text
                or analysis.get("voiceover_text")
                or project.get("source_url")
                or "",
                "source_refs": request.source_refs
                or [value for value in (project.get("source_material_id"), project.get("source_url")) if value],
            }
        )
        tool_name, artifact_name = "competitor_research", "research_brief"
    elif action == "strategy":
        direct_research = (request.source_text or request.prompt or "").strip()
        research_brief = request.input_json or (
            {
                "version": "1.0",
                "project_id": project_id,
                "source_refs": request.source_refs or [],
                "viral_patterns": [],
                "audience_insights": [],
                "pacing_notes": [],
                "content_risks": [],
                "source_summary": direct_research,
            }
            if direct_research
            else _load_artifact(project_id, "research_brief")
        )
        payload.update(
            {
                "research_brief": research_brief,
                "product_guardrails": product_library.product_guardrail_text(project["product_id"]),
            }
        )
        tool_name, artifact_name = "content_strategy", "strategy_brief"
    elif action == "script":
        source = (request.source_text or request.prompt or "").strip()
        payload.update({
            "product_id": request.product_id,
            "analysis_report": {"project_id": project_id, "voiceover_text": source, "hook_3s": source[:120], "structure": []},
            "strategy_brief": {"content_direction": source, "product_guardrails": product_library.product_guardrail_text(request.product_id)},
        })
        tool_name, artifact_name = "doubao_script", "script_copy"
    elif action == "storyboard":
        base_prompt = (request.prompt or request.source_text or "Product scene").strip()
        script = request.input_json
        if script is None:
            script_result = tool_registry.execute_tool(
                "doubao_script",
                {
                    "project_id": project_id,
                    "product_id": request.product_id,
                    "analysis_report": {
                        "project_id": project_id,
                        "voiceover_text": base_prompt,
                        "hook_3s": base_prompt[:120],
                        "structure": [],
                    },
                    "strategy_brief": {
                        "content_direction": base_prompt,
                        "product_guardrails": product_library.product_guardrail_text(request.product_id),
                        "required_story": "scene -> pain -> product solution -> safe demo -> CTA",
                    },
                },
                context={"mock": request.mock, "run_root": root},
            )
            if not script_result.ok:
                error = script_result.error or {"message": "script foundation failed"}
                raise HTTPException(status_code=422, detail=error.get("message") or error)
            script = script_result.data["script_copy"]
            artifacts.save_artifact(project_id, "script_copy", script, run_root=root)
        payload["script_copy"] = script
        tool_name, artifact_name = "doubao_shotplan", "shot_plan"
    elif action == "production":
        prompt = (request.prompt or request.source_text or "Create a product-safe vertical shot").strip()
        source = product_library.resolve_seedance_source(request.product_id)
        references = product_library.resolve_generation_references(request.product_id)
        payload.update({
            "shot": {"number": 1, "visual": prompt, "seedance_prompt": prompt, "reference_paths": references, "camera_motion": {"duration_sec": 6}},
            "shot_index": 1,
            "take_id": "A",
            "asset_manifest": {"version": "2.0", "project_id": project_id, "product_id": request.product_id, "seedance_source": source, "reference_paths": references, "hero_frames": [{"number": 1, "path": source, "source_refs": [source, *references], "status": "approved"}]},
        })
        tool_name, artifact_name = "seedance_shot", "shot_report"
    elif action == "script_breakdown":
        script = request.input_json
        if script is None:
            source = (request.source_text or request.prompt or "").strip()
            if source:
                script_result = tool_registry.execute_tool(
                    "doubao_script",
                    {
                        "project_id": project_id,
                        "product_id": request.product_id,
                        "analysis_report": {
                            "project_id": project_id,
                            "voiceover_text": source,
                            "hook_3s": source[:120],
                            "structure": [],
                        },
                        "strategy_brief": {
                            "content_direction": source,
                            "product_guardrails": product_library.product_guardrail_text(request.product_id),
                        },
                    },
                    context={"mock": request.mock, "run_root": root},
                )
                if not script_result.ok:
                    error = script_result.error or {"message": "script foundation failed"}
                    raise HTTPException(status_code=422, detail=error.get("message") or error)
                script = script_result.data["script_copy"]
                artifacts.save_artifact(project_id, "script_copy", script, run_root=root)
            else:
                script = _load_artifact(project_id, "script_copy")
        payload["script_copy"] = script
        tool_name, artifact_name = "script_breakdown", "script_breakdown"
    elif action == "review":
        script = request.input_json
        if script is None:
            source = (request.source_text or request.prompt or "").strip()
            if not source:
                raise HTTPException(status_code=400, detail="独立审核需要脚本文本、内容需求或 script_copy JSON")
            script_result = tool_registry.execute_tool(
                "doubao_script",
                {
                    "project_id": project_id,
                    "product_id": request.product_id,
                    "analysis_report": {
                        "project_id": project_id,
                        "voiceover_text": source,
                        "hook_3s": source[:120],
                        "structure": [],
                    },
                    "strategy_brief": {
                        "content_direction": source,
                        "product_guardrails": product_library.product_guardrail_text(request.product_id),
                    },
                },
                context={"mock": request.mock, "run_root": root},
            )
            if not script_result.ok:
                error = script_result.error or {"message": "script foundation failed"}
                raise HTTPException(status_code=422, detail=error.get("message") or error)
            script = script_result.data["script_copy"]
            artifacts.save_artifact(project_id, "script_copy", script, run_root=root)
        payload.update(
            {
                "script_copy": script,
                "analysis_report": _load_artifact_or_none(project_id, "analysis_report") or {},
            }
        )
        tool_name, artifact_name = "doubao_review", "review_report"
    elif action == "feedback":
        text = (request.source_text or request.prompt or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="独立反馈需要输入复盘结论或优化要求")
        if len(text) > 1000:
            raise HTTPException(status_code=400, detail="反馈内容不能超过 1000 字")
        artifact_name = "feedback_record"
        artifact = {
            "version": "1.0",
            "project_id": project_id,
            "author": "operator",
            "text": text,
            "created_at": queue.utc_now(),
        }
        artifacts.save_artifact(project_id, artifact_name, artifact, run_root=root)
        feedback_root = _feedback_root()
        feedback_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        _atomic_write_json(feedback_root / f"{project_id}-{stamp}-{secrets.token_hex(2)}.json", artifact)
        queue.record_event(
            project_id=project_id,
            event_type="feedback.created",
            message=text[:120],
            meta={"standalone": standalone},
            db_path=_db_path(),
        )
        return {
            "ok": True,
            "project_id": project_id,
            "action": action,
            "artifact_name": artifact_name,
            "artifact": artifact,
            "download_url": f"/api/v2/artifacts/{project_id}/{artifact_name}/download",
            "meta": {"tool": "feedback_library", "standalone": standalone},
        }
    else:
        raise HTTPException(status_code=400, detail="action must be collector, analysis, research, strategy, script, script_breakdown, storyboard, production, review, or feedback")

    result = tool_registry.execute_tool(
        tool_name,
        payload,
        context={"mock": request.mock, "run_root": root},
    )
    if not result.ok:
        error = result.error or {"message": f"{tool_name} failed"}
        raise HTTPException(status_code=422, detail=error.get("message") or error)
    artifact = result.data[artifact_name]
    artifacts.save_artifact(project_id, artifact_name, artifact, run_root=root)
    queue.record_event(
        project_id=project_id,
        event_type="agent.capability_completed",
        message=action,
        meta={"tool": tool_name, "artifact": artifact_name, "mock": request.mock},
        db_path=_db_path(),
    )
    return {
        "ok": True,
        "project_id": project_id,
        "action": action,
        "artifact_name": artifact_name,
        "artifact": artifact,
        "download_url": f"/api/v2/artifacts/{project_id}/{artifact_name}/download",
        "meta": result.meta,
    }


@app.get("/api/v2/products")
def products(refresh: bool = Query(default=False)) -> dict[str, Any]:
    index = _load_product_library(refresh=refresh)
    return {
        "items": _list_products(index),
        "generated_at": index.get("generated_at"),
        "source_roots": index.get("source_roots", []),
    }


@app.get("/api/v2/product-library")
def product_library_index(refresh: bool = Query(default=False)) -> dict[str, Any]:
    return _load_product_library(refresh=refresh)


@app.post("/api/v2/product-library/refresh")
def refresh_product_library(request: ProductLibraryRefreshRequest | None = None) -> dict[str, Any]:
    return product_library.refresh_index((request.source_roots if request else None))


@app.get("/api/v2/product-library/{product_id}")
def product_library_product(product_id: str) -> dict[str, Any]:
    product = product_library.get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@app.post("/api/v2/collect/manual")
def collect_manual(request: ManualCollectRequest) -> dict[str, Any]:
    payload = {
        "links_text": request.links_text,
        "urls": request.urls or [],
        "items": request.items or [],
        "product_id": request.product_id,
        "source_keyword": request.source_keyword,
        "library_root": _material_library_root().as_posix(),
    }
    result = manual_import.execute(payload, context=_tool_context())
    if not result.ok:
        error = result.error or {"message": "manual import failed"}
        status_code = 422 if error.get("category") == "validation" else 500
        raise HTTPException(status_code=status_code, detail=error.get("message") or error)
    queue.record_event(
        event_type="collector.manual_import",
        message=f"{result.data['imported_count']} links",
        meta={"library_root": result.data["library_root"]},
        db_path=_db_path(),
    )
    return result.data


@app.post("/api/v2/collect/tiktok")
def collect_tiktok(request: TikTokCollectRequest) -> dict[str, Any]:
    payload = {
        "links_text": request.links_text,
        "urls": request.urls or [],
        "items": request.items or [],
        "product_id": request.product_id,
        "source_keyword": request.source_keyword,
        "library_root": _material_library_root().as_posix(),
    }
    result = tiktok_oembed.execute(payload, context=_tool_context())
    if not result.ok:
        error = result.error or {"message": "TikTok collection failed"}
        status_code = 422 if error.get("category") == "validation" else 502
        raise HTTPException(status_code=status_code, detail=error.get("message") or error)
    queue.record_event(
        event_type="collector.tiktok_oembed",
        message=f"{result.data['imported_count']} links",
        meta={
            "library_root": result.data["library_root"],
            "failed_count": result.data["failed_count"],
        },
        db_path=_db_path(),
    )
    return result.data


@app.post("/api/v2/collect/tiktok/run")
def collect_tiktok_and_run(request: TikTokIntakeRunRequest) -> dict[str, Any]:
    root = _material_library_root()
    collect_payload = {
        "urls": [request.url],
        "product_id": request.product_id,
        "source_keyword": "tiktok_active_capture",
        "library_root": root.as_posix(),
    }
    collector = manual_import.execute if request.mock else tiktok_oembed.execute
    collected = collector(collect_payload, context=_tool_context(mock=request.mock))
    if not collected.ok:
        error = collected.error or {"category": "provider", "message": "TikTok collection failed"}
        raise HTTPException(status_code=422 if error.get("category") == "validation" else 502, detail=error["message"])

    item = collected.data["items"][0]
    material_id = str(item["material_id"])
    material_dir = root / material_id
    captured = tool_registry.execute_tool(
        "tiktok_video",
        {
            "url": request.url,
            "material_dir": material_dir.as_posix(),
            "transcript_text": request.transcript_text or "",
        },
        context={"mock": request.mock},
    )
    if not captured.ok:
        error = captured.error or {"category": "provider", "message": "TikTok capture failed"}
        raise HTTPException(status_code=422 if error.get("category") == "validation" else 502, detail=error["message"])

    capture = captured.data
    current = manual_import.load_material_meta(material_id, root)
    intake = dict(current.get("asset_intake") or {})
    intake["notes"] = (
        "Active TikTok capture completed. Reference use only: structure, pacing, hook style, shot rhythm, and audience insight."
    )
    meta = manual_import.update_material_meta(
        material_id,
        {
            "processing_status": "captured" if capture.get("local_video_path") else "metadata_only",
            "transcript_text": str(capture.get("transcript_text") or "")[:12000],
            "local_video_path": str(capture.get("local_video_path") or ""),
            "local_cover_path": str(capture.get("local_cover_path") or ""),
            "ai_analysis_json": json.dumps(
                {
                    "capture_status": capture.get("status"),
                    "transcript_source": capture.get("transcript_source"),
                    "frame_paths": capture.get("frame_paths") or [],
                },
                ensure_ascii=False,
            ),
            "asset_intake": intake,
            "source_mode": "mock" if request.mock else "real",
            **_discovery_meta_updates(request.source_item),
        },
        root,
    )

    project_id = _validate_project_id(request.project_id or _new_project_id())
    run_root = _run_root(project_id)
    source_text = str(meta.get("transcript_text") or meta.get("caption") or "")[:8000]
    task_id = engine.start_pipeline(
        project_id,
        product_id=request.product_id,
        source_material_id=material_id,
        source_url=request.url,
        source_text=source_text,
        db_path=_db_path(),
        run_root=run_root,
        mock=request.mock,
    )
    status = engine.run_until_blocked(project_id, db_path=_db_path(), run_root=run_root, mock=request.mock)
    analysis = _load_artifact_or_none(project_id, "analysis_report") or {}
    if analysis:
        meta = manual_import.update_material_meta(
            material_id,
            {
                "processing_status": "analyzed",
                "ai_analysis_json": json.dumps(
                    {
                        "capture_status": capture.get("status"),
                        "transcript_source": capture.get("transcript_source"),
                        "frame_paths": capture.get("frame_paths") or [],
                        "analysis": {
                            "hook_3s": analysis.get("hook_3s"),
                            "structure": analysis.get("structure") or [],
                            "pacing": analysis.get("pacing") or [],
                            "keyframes": analysis.get("keyframes") or [],
                            "shot_breakdown": analysis.get("shot_breakdown") or [],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
            root,
        )
    queue.record_event(
        project_id=project_id,
        event_type="collector.tiktok_active_capture",
        message=material_id,
        meta={"mock": request.mock, "transcript_source": capture.get("transcript_source")},
        db_path=_db_path(),
    )
    return {
        "ok": True,
        "material": meta,
        "capture": capture,
        "project_id": project_id,
        "task_id": task_id,
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
        "warnings": [] if capture.get("transcript_text") else ["未取得字幕，请在研究节点补充转写后重新运行研究分析。"],
    }


@app.post("/api/v2/collect/tiktok/crawl")
def crawl_tiktok_and_run(request: TikTokCrawlRequest) -> dict[str, Any]:
    limit = max(1, min(request.limit, 20))
    discovered = tool_registry.execute_tool(
        "tiktok_crawler",
        {
            "target_type": request.target_type,
            "provider": request.provider,
            "target": request.target,
            "limit": limit,
        },
        context={"mock": request.mock, "env": os.environ},
    )
    if not discovered.ok:
        error = discovered.error or {"category": "provider", "message": "TikTok crawl failed"}
        status_code = 400 if error.get("category") == "validation" else 503 if error.get("category") == "not_configured" else 502
        raise HTTPException(status_code=status_code, detail=error["message"])

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for item in discovered.data.get("items", [])[:limit]:
        url = str(item.get("url") or "")
        try:
            result = collect_tiktok_and_run(
                TikTokIntakeRunRequest(
                    url=url,
                    product_id=request.product_id,
                    transcript_text=str(item.get("caption") or "") or None,
                    source_item=item,
                    mock=request.mock,
                )
            )
            results.append(
                {
                    "url": url,
                    "material_id": result["material"]["material_id"],
                    "project_id": result["project_id"],
                    "stage": result["engine"]["stage"],
                    "warnings": result["warnings"],
                }
            )
        except HTTPException as exc:
            failures.append({"url": url, "error": str(exc.detail)})
    queue.record_event(
        event_type="collector.tiktok_crawl_completed",
        message=f"{len(results)}/{len(discovered.data.get('items', []))} videos",
        meta={"provider": discovered.data.get("provider"), "target_type": request.target_type, "target": request.target},
        db_path=_db_path(),
    )
    return {
        "ok": bool(results),
        "provider": discovered.data.get("provider"),
        "target_type": request.target_type,
        "target": request.target,
        "discovered_count": len(discovered.data.get("items", [])),
        "completed_count": len(results),
        "failed_count": len(failures),
        "results": results,
        "failures": failures,
    }


@app.get("/api/v2/collect/tiktok/auto")
def get_auto_collector_settings() -> dict[str, Any]:
    return _auto_collector_settings()


@app.put("/api/v2/collect/tiktok/auto")
def update_auto_collector_settings(request: AutoCollectorSettingsRequest) -> dict[str, Any]:
    if request.target_type not in {"keyword", "account", "hashtag", "trending"}:
        raise HTTPException(status_code=422, detail="不支持的发现方式")
    if request.target_type != "trending" and not request.target.strip():
        raise HTTPException(status_code=422, detail="请填写自动采集目标")
    if request.provider not in {"auto", "tiktok_api", "apify", "yt_dlp"}:
        raise HTTPException(status_code=422, detail="不支持的采集后端")
    _save_auto_collector_settings(request)
    return _auto_collector_settings()


@app.post("/api/v2/collect/tiktok/auto/run-now")
async def run_auto_collector_now() -> dict[str, Any]:
    result = await asyncio.to_thread(_run_auto_collector_once, True)
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return result


def _discovery_meta_updates(item: dict[str, Any] | None) -> dict[str, Any]:
    item = item or {}
    return {
        "video_title": str(item.get("title") or item.get("caption") or "")[:300],
        "caption": str(item.get("caption") or "")[:2000],
        "author_name": str(item.get("author_name") or item.get("author") or "")[:200],
        "author_url": str(item.get("author_url") or "")[:1000],
        "cover_url": str(item.get("cover_url") or item.get("thumbnail_url") or "")[:2000],
        "like_count": _nonnegative_int(item.get("like_count")),
        "comment_count": _nonnegative_int(item.get("comment_count")),
        "share_count": _nonnegative_int(item.get("share_count")),
    }


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name) or "").strip().casefold()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _ensure_auto_collector_settings() -> None:
    queue.init_db(db_path=_db_path())
    target = str(os.environ.get("VAF_AUTO_COLLECT_TARGET") or "").strip()
    enabled = int(_env_bool("VAF_AUTO_COLLECT_ENABLED", False) and bool(target))
    target_type = str(os.environ.get("VAF_AUTO_COLLECT_TARGET_TYPE") or "keyword").strip()
    provider = str(os.environ.get("VAF_AUTO_COLLECT_PROVIDER") or "auto").strip()
    try:
        limit = max(1, min(int(os.environ.get("VAF_AUTO_COLLECT_LIMIT") or 3), 20))
        interval = max(10, min(int(os.environ.get("VAF_AUTO_COLLECT_INTERVAL_MINUTES") or 60), 1440))
    except ValueError:
        limit, interval = 3, 60
    with queue.get_conn(_db_path()) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO collector_schedules
            (id, enabled, target_type, provider, target, limit_count, interval_minutes, product_id, mock, status, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?)
            """,
            (
                enabled,
                target_type if target_type in {"keyword", "account", "hashtag", "trending"} else "keyword",
                provider if provider in {"auto", "tiktok_api", "apify", "yt_dlp"} else "auto",
                target,
                limit,
                interval,
                str(os.environ.get("VAF_PRODUCT_ID") or "便携恒温杯"),
                int(not _env_bool("VAF_AUTO_COLLECT_REAL", False)),
                queue.utc_now(),
            ),
        )


def _auto_collector_settings() -> dict[str, Any]:
    _ensure_auto_collector_settings()
    with queue.get_conn(_db_path()) as conn:
        row = conn.execute("SELECT * FROM collector_schedules WHERE id = 1").fetchone()
    payload = dict(row or {})
    return {
        "enabled": bool(payload.get("enabled")),
        "target_type": payload.get("target_type") or "keyword",
        "provider": payload.get("provider") or "auto",
        "target": payload.get("target") or "",
        "limit": int(payload.get("limit_count") or 3),
        "interval_minutes": int(payload.get("interval_minutes") or 60),
        "product_id": payload.get("product_id") or "便携恒温杯",
        "mock": bool(payload.get("mock")),
        "status": payload.get("status") or "idle",
        "last_started_at": payload.get("last_started_at"),
        "last_finished_at": payload.get("last_finished_at"),
        "last_message": payload.get("last_message") or "",
        "failure_count": int(payload.get("failure_count") or 0),
        "next_run_at": payload.get("next_run_at"),
        "updated_at": payload.get("updated_at"),
    }


def _save_auto_collector_settings(request: AutoCollectorSettingsRequest) -> None:
    _ensure_auto_collector_settings()
    with queue.get_conn(_db_path()) as conn:
        conn.execute(
            """
            UPDATE collector_schedules
            SET enabled = ?, target_type = ?, provider = ?, target = ?, limit_count = ?, interval_minutes = ?,
                product_id = ?, mock = ?, status = CASE WHEN status = 'running' THEN status ELSE 'idle' END,
                last_message = CASE WHEN status = 'running' THEN last_message ELSE '' END,
                failure_count = CASE WHEN status = 'running' THEN failure_count ELSE 0 END,
                next_run_at = CASE WHEN status = 'running' THEN next_run_at ELSE NULL END,
                updated_at = ?
            WHERE id = 1
            """,
            (
                int(request.enabled), request.target_type, request.provider, request.target.strip(),
                max(1, min(request.limit, 20)), max(10, min(request.interval_minutes, 1440)),
                request.product_id, int(request.mock), queue.utc_now(),
            ),
        )


def _auto_collector_due(settings: dict[str, Any]) -> bool:
    if not settings["enabled"] or settings["status"] == "running":
        return False
    if settings["target_type"] != "trending" and not settings["target"].strip():
        return False
    retry_at = _parse_utc_timestamp(settings.get("next_run_at"))
    if retry_at is not None:
        return datetime.now(timezone.utc) >= retry_at
    last_finished = str(settings.get("last_finished_at") or "")
    if not last_finished:
        return True
    try:
        completed = datetime.fromisoformat(last_finished.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - completed).total_seconds() >= settings["interval_minutes"] * 60


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _collector_retry_delay_seconds(failure_count: int, interval_minutes: int) -> int:
    return min(max(60, interval_minutes * 60), 60 * (2 ** min(max(failure_count, 1), 6)))


def _recover_auto_collector_on_startup() -> None:
    """Release a schedule abandoned by a process restart without losing its error history."""
    with queue.get_conn(_db_path()) as conn:
        row = conn.execute("SELECT status, failure_count, interval_minutes FROM collector_schedules WHERE id = 1").fetchone()
        if row is None or row["status"] != "running":
            return
        failure_count = int(row["failure_count"] or 0) + 1
        retry_after = _collector_retry_delay_seconds(failure_count, int(row["interval_minutes"] or 60))
        now = queue.utc_now()
        retry_at = (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        conn.execute(
            """
            UPDATE collector_schedules
            SET status = 'failed', failure_count = ?, next_run_at = ?, last_finished_at = ?,
                last_message = '服务重启后恢复：上一次采集任务未完成，将按退避策略重试', updated_at = ?
            WHERE id = 1
            """,
            (failure_count, retry_at, now, now),
        )


def _run_auto_collector_once(force: bool = False) -> dict[str, Any]:
    settings = _auto_collector_settings()
    if not force and not _auto_collector_due(settings):
        return {"ok": True, "ran": False, "settings": settings}
    if settings["target_type"] != "trending" and not settings["target"].strip():
        return {"ok": False, "ran": False, "error": "请先设置自动采集目标", "settings": settings}
    failure_count = int(settings.get("failure_count") or 0)
    with queue.get_conn(_db_path()) as conn:
        claimed = conn.execute(
            """
            UPDATE collector_schedules
            SET status = 'running', last_started_at = ?, last_message = '正在发现、下载并分析素材', updated_at = ?
            WHERE id = 1 AND status != 'running'
            """,
            (queue.utc_now(), queue.utc_now()),
        ).rowcount
    if not claimed:
        return {"ok": True, "ran": False, "settings": _auto_collector_settings()}
    try:
        result = crawl_tiktok_and_run(
            TikTokCrawlRequest(
                target_type=settings["target_type"], provider=settings["provider"], target=settings["target"],
                limit=settings["limit"], product_id=settings["product_id"], mock=settings["mock"],
            )
        )
        message = f"发现 {result['discovered_count']} 条，完成 {result['completed_count']} 条，失败 {result['failed_count']} 条"
        outcome = {"ok": bool(result["ok"]), "ran": True, "result": result}
    except HTTPException as exc:
        message = str(exc.detail)
        outcome = {"ok": False, "ran": True, "error": message}
    except Exception as exc:  # Defensive: a scheduler fault must not stop the API process.
        message = str(exc)
        outcome = {"ok": False, "ran": True, "error": message}
    next_run_at = None
    if not outcome["ok"]:
        failure_count += 1
        retry_after = _collector_retry_delay_seconds(failure_count, settings["interval_minutes"])
        next_run_at = (datetime.now(timezone.utc) + timedelta(seconds=retry_after)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        message = f"{message}；将在约 {max(1, retry_after // 60)} 分钟后重试"
    with queue.get_conn(_db_path()) as conn:
        conn.execute(
            """
            UPDATE collector_schedules
            SET status = ?, last_finished_at = ?, last_message = ?, failure_count = ?, next_run_at = ?, updated_at = ?
            WHERE id = 1
            """,
            (
                "idle" if outcome["ok"] else "failed",
                queue.utc_now(),
                message[:1000],
                0 if outcome["ok"] else failure_count,
                next_run_at,
                queue.utc_now(),
            ),
        )
    outcome["settings"] = _auto_collector_settings()
    return outcome


async def _auto_collector_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_run_auto_collector_once)
        except Exception:
            # Settings and errors remain visible through the collection endpoint; keep the scheduler alive.
            pass
        await asyncio.sleep(20)


def _auth_enabled() -> bool:
    return _env_bool("VAF_AUTH_ENABLED", False)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(store: dict[str, deque[float]], key: str, window_s: int, limit: int) -> bool:
    now = time.monotonic()
    attempts = store[key]
    while attempts and now - attempts[0] >= window_s:
        attempts.popleft()
    return len(attempts) >= limit


def _record_attempt(store: dict[str, deque[float]], key: str, window_s: int) -> None:
    now = time.monotonic()
    attempts = store[key]
    while attempts and now - attempts[0] >= window_s:
        attempts.popleft()
    attempts.append(now)


def _self_registration_enabled() -> bool:
    return _env_bool("VAF_SELF_REGISTRATION_ENABLED", True)


def _auth_configuration_error() -> str | None:
    if len(str(os.environ.get("VAF_SESSION_SECRET") or "").strip()) < 32:
        return "VAF_SESSION_SECRET must contain at least 32 characters"
    return None


def _session_secret() -> bytes:
    configured = str(os.environ.get("VAF_SESSION_SECRET") or "").strip()
    if _auth_enabled() and len(configured) < 32:
        raise ValueError("invalid session secret")
    return (configured or "local-development-session-secret").encode("utf-8")


def _sign_session(username: str, role: str) -> str:
    payload = json.dumps(
        {"username": username, "role": role, "exp": int(time.time()) + 8 * 60 * 60},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    signature = hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _read_session(request: Request) -> dict[str, Any] | None:
    token = str(request.cookies.get("vaf_session") or "")
    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(_session_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding).decode("utf-8"))
        if int(payload.get("exp") or 0) < int(time.time()):
            return None
        if payload.get("role") not in {"operator", "admin"}:
            return None
        username = str(payload.get("username") or "")
        role = str(payload["role"])
        if _auth_enabled():
            account = user_store.get_user_by_username(username, db_path=_db_path())
            if account is None or account.get("status") != "active" or account.get("role") != role:
                return None
        return {"username": username, "role": role}
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _path_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


@app.get("/api/v2/collect/library")
def collect_library(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    root = _material_library_root()
    index = manual_import.load_library_index(root)
    items = index.get("items", [])[:limit]
    enriched = []
    for item in items:
        payload = dict(item)
        try:
            meta = manual_import.load_material_meta(str(item["material_id"]), root)
        except (FileNotFoundError, ValueError):
            meta = None
        payload["material_meta"] = meta
        enriched.append(payload)
    return {"library_root": root.as_posix(), "items": enriched}


@app.get("/api/v2/collect/materials/{material_id}")
def collect_material(material_id: str) -> dict[str, Any]:
    try:
        root = _material_library_root()
        payload = manual_import.load_material_meta(material_id, root)
        material_dir = (root / material_id).resolve()
        files: list[dict[str, Any]] = []
        if material_dir.is_dir():
            for path in sorted(item for item in material_dir.rglob("*") if item.is_file()):
                relative = path.relative_to(material_dir).as_posix()
                files.append(
                    {
                        "path": relative,
                        "size_bytes": path.stat().st_size,
                        "download_url": f"/api/v2/collect/materials/{material_id}/file/{relative}",
                    }
                )
        payload["files"] = files
        payload["transcript_status"] = "ready" if str(payload.get("transcript_text") or "").strip() else "missing"
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v2/collect/materials/{material_id}/file/{relative_path:path}")
def collect_material_file(material_id: str, relative_path: str) -> FileResponse:
    """Serve only files stored inside one material directory."""
    root = _material_library_root()
    material_dir = (root / material_id).resolve()
    target = (material_dir / relative_path).resolve()
    try:
        target.relative_to(material_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid material file path") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="material file not found")
    return FileResponse(target)


@app.post("/api/v2/pipeline/run")
def run_pipeline(request: PipelineRunRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id or _new_project_id())
    if not request.mock:
        missing = [name for name in ("DOUBAO_API_KEY", "SEEDANCE_API_KEY") if not os.environ.get(name)]
        if missing:
            raise HTTPException(status_code=422, detail=f"真实运行缺少配置：{', '.join(missing)}。请在服务器 .env.local 配置后重试。")
    source_link_id = _normalize_source_link_id(request.source_link_id, request.link_id)
    source_meta = _source_material_or_none(request.source_material_id)
    if not request.mock and source_meta and str(source_meta.get("source_mode") or "") == "mock":
        raise HTTPException(status_code=409, detail="真实运行不能使用演练素材，请重新抓取真实 TikTok 来源")
    product_id = request.product_id or str((source_meta or {}).get("product_id") or "便携恒温杯")
    run_root = _run_root(project_id)
    task_id = engine.start_pipeline(
        project_id,
        product_id=product_id,
        source_link_id=source_link_id,
        source_material_id=request.source_material_id,
        source_url=str((source_meta or {}).get("source_url") or ""),
        source_text=(
            request.source_text
            or str((source_meta or {}).get("transcript_text") or "")
            or str((source_meta or {}).get("caption") or "")
        )[:8000],
        db_path=_db_path(),
        run_root=run_root,
        mock=request.mock,
    )
    status = engine.run_until_blocked(
        project_id,
        db_path=_db_path(),
        run_root=run_root,
        mock=request.mock,
    )
    return {
        "project_id": project_id,
        "task_id": task_id,
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
    }


@app.get("/api/v2/pipeline")
def list_pipeline(
    limit: int = Query(default=50, ge=1, le=200),
    include_standalone: bool = Query(default=False),
) -> dict[str, Any]:
    with queue.get_conn(_db_path()) as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC, id DESC LIMIT ?",
            (200,),
        ).fetchall()
    if not include_standalone:
        rows = [row for row in rows if not _is_standalone_project(row)]
    return {"items": [_project_summary(str(row["id"]), row=row) for row in rows[:limit]]}


@app.get("/api/v2/pipeline/{project_id}")
def get_pipeline(project_id: str) -> dict[str, Any]:
    return _project_summary(_validate_project_id(project_id))


@app.delete("/api/v2/pipeline/{project_id}")
def delete_pipeline(project_id: str) -> dict[str, Any]:
    project_id = _validate_project_id(project_id)
    row = _project_row_or_none(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    run_root = _run_root(project_id).resolve()
    runs_root = _runs_root().resolve()
    try:
        queue.delete_project(project_id, db_path=_db_path())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="项目仍在运行，无法删除") from exc
    if run_root.is_relative_to(runs_root) and run_root.exists():
        shutil.rmtree(run_root)
    return {"ok": True, "project_id": project_id}


@app.get("/api/v2/reports/{project_id}")
def get_run_report(project_id: str) -> dict[str, Any]:
    return _run_report(_validate_project_id(project_id))


@app.get("/api/v2/artifacts/{project_id}/{artifact_name}")
def get_artifact(project_id: str, artifact_name: str) -> dict[str, Any]:
    project_id = _validate_project_id(project_id)
    artifact_name = _validate_artifact_name(artifact_name)
    payload = _load_artifact(project_id, artifact_name)
    if artifact_name == "asset_manifest":
        _attach_preview_urls(project_id, payload)
    if artifact_name == "take_manifest":
        _attach_take_media_status(project_id, payload)
    return payload


@app.get("/api/v2/artifacts/{project_id}/{artifact_name}/download")
def download_artifact(project_id: str, artifact_name: str) -> FileResponse:
    project_id = _validate_project_id(project_id)
    artifact_name = _validate_artifact_name(artifact_name)
    path = _artifact_path(project_id, artifact_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{artifact_name} not found")
    return FileResponse(
        path,
        media_type="application/json",
        filename=f"{project_id}-{artifact_name}.json",
    )


@app.put("/api/v2/artifacts/{project_id}/{artifact_name}")
def put_artifact(
    project_id: str,
    artifact_name: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    project_id = _validate_project_id(project_id)
    artifact_name = _validate_artifact_name(artifact_name)
    if artifact_name not in {"script_copy", "shot_plan"}:
        raise HTTPException(status_code=400, detail="only script_copy and shot_plan can be edited")
    if payload.get("project_id") != project_id:
        raise HTTPException(status_code=400, detail="artifact project_id does not match URL")

    old_payload = _load_artifact_or_none(project_id, artifact_name)
    stale_sections = (
        _changed_script_sections(old_payload, payload)
        if artifact_name == "script_copy"
        else _changed_shots(old_payload, payload)
    )
    try:
        artifacts.save_artifact(
            project_id,
            artifact_name,
            payload,
            run_root=_run_root(project_id),
            script_copy=(
                _load_artifact(project_id, "script_copy")
                if artifact_name == "shot_plan"
                else None
            ),
        )
    except artifacts.ArtifactValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"pointer": issue.pointer, "message": issue.message}
                for issue in exc.issues
            ],
        ) from exc

    if artifact_name == "script_copy":
        _refresh_script_gate_checkpoint(project_id, stale_sections)
    queue.record_event(
        project_id=project_id,
        event_type="artifact.saved",
        message=artifact_name,
        meta={"stale_sections": stale_sections},
        db_path=_db_path(),
    )
    return {
        "ok": True,
        "project_id": project_id,
        "artifact_name": artifact_name,
        "stale_sections": stale_sections,
        "artifact": payload,
    }


@app.post("/api/v2/manual/run")
def run_manual_stage(request: ManualStageRunRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    root = _run_root(project_id)
    revision = queue.utc_now()
    stage = request.stage.strip().casefold()

    if stage == "script":
        task_stage, agent, payload = "script", "script", {
            "run_root": root.as_posix(),
            "rewrite_reason": "manual workbench regeneration",
            "revision": revision,
        }
    elif stage == "storyboard":
        _require_approved_gate(project_id, "script_gate", root)
        _load_artifact(project_id, "script_copy")
        task_stage, agent, payload = "storyboard", "storyboard", {
            "run_root": root.as_posix(),
            "revision": revision,
        }
    elif stage == "production":
        _require_approved_gate(project_id, "hero_gate", root)
        if request.shot_index is None or request.shot_index < 1:
            raise HTTPException(status_code=400, detail="production requires shot_index >= 1")
        shot_plan = _load_artifact(project_id, "shot_plan")
        shot = next(
            (item for item in shot_plan.get("shots", []) if int(item.get("number") or 0) == request.shot_index),
            None,
        )
        if shot is None:
            raise HTTPException(status_code=404, detail=f"shot {request.shot_index} not found")
        _load_artifact(project_id, "asset_manifest")
        task_stage, agent, payload = "production", "media", {
            "run_root": root.as_posix(),
            "shot_index": request.shot_index,
            "shot": shot,
            "revision": revision,
            "manual_only": True,
            "take_id": request.take_id,
        }
    elif stage == "compose":
        _require_approved_gate(project_id, "hero_gate", root)
        _require_selected_playable_takes(project_id, root)
        _load_artifact(project_id, "shot_report")
        task_stage, agent, payload = "compose", "media", {
            "run_root": root.as_posix(),
            "revision": revision,
        }
    else:
        raise HTTPException(status_code=400, detail="stage must be script, storyboard, production, or compose")

    checkpoint.write_checkpoint(
        project_id,
        task_stage,
        status="queued",
        data={"manual": True, "revision": revision},
        run_root=root,
    )
    task_id = queue.enqueue_task(
        project_id=project_id,
        stage=task_stage,
        agent=agent,
        payload=payload,
        db_path=_db_path(),
    )
    queue.record_event(
        project_id=project_id,
        task_id=task_id,
        event_type="manual.stage_requested",
        message=task_stage,
        meta={"shot_index": request.shot_index, "revision": revision},
        db_path=_db_path(),
    )
    if stage in {"production", "compose"}:
        status = engine.run_task(task_id, db_path=_db_path(), run_root=root, mock=request.mock)
    else:
        status = engine.run_until_blocked(
            project_id, db_path=_db_path(), run_root=root, mock=request.mock
        )
    return {
        "task_id": task_id,
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
    }


@app.post("/api/v2/takes/select")
def select_take(request: TakeSelectRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    root = _run_root(project_id)
    manifest = _load_artifact(project_id, "take_manifest")
    shot_entry = next((item for item in manifest.get("shots", []) if int(item.get("number") or 0) == request.shot_index), None)
    if shot_entry is None:
        raise HTTPException(status_code=404, detail=f"shot {request.shot_index} has no generated takes")
    selected = next((item for item in shot_entry.get("takes", []) if item.get("take_id") == request.take_id), None)
    if selected is None:
        raise HTTPException(status_code=404, detail=f"take {request.take_id} not found")
    if selected.get("status") != "qa_pass":
        raise HTTPException(status_code=409, detail="该 Take 尚未通过单镜质检，不能选用或参与合成")
    if not _is_playable_take_path(root, str(selected.get("path") or "")):
        raise HTTPException(status_code=409, detail="该 Take 不是可播放的真实媒体，不能选用或参与合成")
    shot_entry["selected_take_id"] = request.take_id
    for item in shot_entry.get("takes", []):
        if item.get("take_id") == request.take_id:
            item["status"] = "selected"
        elif item.get("status") == "selected":
            item["status"] = "qa_pass"
    artifacts.save_artifact(project_id, "take_manifest", manifest, run_root=root)

    report = _load_artifact_or_none(project_id, "shot_report") or {"version": "2.0", "project_id": project_id, "shots": []}
    by_number = {int(item["number"]): item for item in report.get("shots", [])}
    by_number[request.shot_index] = {
        "number": request.shot_index,
        "status": "succeeded",
        "path": selected["path"],
        "cost_cny": float(selected.get("cost_cny") or 0),
        "attempt": int(selected.get("attempt") or 1),
        "duration_sec": float(selected.get("duration_sec") or 6),
        "take_id": request.take_id,
    }
    report["shots"] = [by_number[number] for number in sorted(by_number)]
    artifacts.save_artifact(project_id, "shot_report", report, run_root=root)
    queue.record_event(project_id=project_id, event_type="take.selected", message=f"shot{request.shot_index}:{request.take_id}", db_path=_db_path())
    return {"ok": True, "take_manifest": manifest, "shot_report": report}


@app.post("/api/v2/takes/review")
def review_take(request: TakeReviewRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    root = _run_root(project_id)
    manifest = _load_artifact(project_id, "take_manifest")
    shot_entry = next((item for item in manifest.get("shots", []) if int(item.get("number") or 0) == request.shot_index), None)
    if shot_entry is None:
        raise HTTPException(status_code=404, detail=f"shot {request.shot_index} has no generated takes")
    take = next((item for item in shot_entry.get("takes", []) if item.get("take_id") == request.take_id), None)
    if take is None:
        raise HTTPException(status_code=404, detail=f"take {request.take_id} not found")
    if not _is_playable_take_path(root, str(take.get("path") or "")):
        raise HTTPException(status_code=409, detail="该 Take 没有可播放的真实媒体，不能进行质检")

    checks = {
        "product_identity": request.product_identity,
        "no_invented_brand": request.no_invented_brand,
        "temperature_display": request.temperature_display,
        "usage_flow": request.usage_flow,
        "continuity": request.continuity,
    }
    approved = all(checks.values())
    take["status"] = "qa_pass" if approved else "rejected"
    take["qa"] = {"approved": approved, "checks": checks, "notes": request.notes.strip()}
    if not approved and shot_entry.get("selected_take_id") == request.take_id:
        shot_entry["selected_take_id"] = None
    artifacts.save_artifact(project_id, "take_manifest", manifest, run_root=root)
    queue.record_event(
        project_id=project_id,
        event_type="take.qa_passed" if approved else "take.rejected",
        message=f"shot{request.shot_index}:{request.take_id}",
        meta={"checks": checks, "notes": request.notes.strip()},
        db_path=_db_path(),
    )
    return {"ok": True, "approved": approved, "take_manifest": manifest}


@app.post("/api/v2/agents/promote")
def promote_standalone_artifact(request: StandalonePromoteRequest) -> dict[str, Any]:
    source_project_id = _validate_project_id(request.source_project_id)
    artifact_name = _validate_artifact_name(request.artifact_name)
    source_row = _project_row_or_none(source_project_id)
    if source_row is None or not _is_standalone_project(source_row):
        raise HTTPException(status_code=409, detail="只能将独立工作区产物转为生产项目")
    if artifact_name not in {"analysis_report", "script_copy", "shot_plan"}:
        raise HTTPException(status_code=400, detail="当前仅支持将分析、脚本或分镜转为生产项目")

    source_root = _run_root(source_project_id)
    artifact = _load_artifact_from_root(source_root, artifact_name)
    project_id = _validate_project_id(request.project_id or _new_project_id())
    product_id = request.product_id or str(artifact.get("product_id") or source_row["product_id"] or "便携恒温杯")
    root = _runs_root() / project_id
    root.mkdir(parents=True, exist_ok=True)
    queue.ensure_project(
        project_id,
        product_id=product_id,
        payload={
            "mock": request.mock,
            "run_root": root.as_posix(),
            "promoted_from": {"project_id": source_project_id, "artifact_name": artifact_name},
        },
        db_path=_db_path(),
    )

    if artifact_name == "analysis_report":
        analysis = _with_project_id(artifact, project_id)
        artifacts.save_artifact(project_id, "analysis_report", analysis, run_root=root)
        start_stage, agent = "research", "analysis"
    else:
        script = _load_artifact_from_root(source_root, "script_copy") if artifact_name == "shot_plan" else artifact
        script = _with_project_id(script, project_id)
        artifacts.save_artifact(project_id, "script_copy", script, run_root=root)
        analysis = _analysis_from_script(script, project_id)
        artifacts.save_artifact(project_id, "analysis_report", analysis, run_root=root)
        if artifact_name == "script_copy":
            start_stage, agent = "script_breakdown", "script"
        else:
            plan = _with_project_id(artifact, project_id)
            plan["script_copy_ref"] = "artifacts/script_copy.json"
            artifacts.save_artifact(project_id, "shot_plan", plan, run_root=root, script_copy=script)
            start_stage, agent = "asset", "asset"

    queue.enqueue_task(
        project_id=project_id,
        stage=start_stage,
        agent=agent,
        payload={"run_root": root.as_posix(), "promoted_from": source_project_id},
        db_path=_db_path(),
    )
    status = engine.run_until_blocked(project_id, db_path=_db_path(), run_root=root, mock=request.mock)
    return {
        "ok": True,
        "project_id": project_id,
        "promoted_from": {"project_id": source_project_id, "artifact_name": artifact_name},
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
    }


@app.post("/api/v2/gates/approve")
def approve_gate(request: GateApproveRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    if request.stage not in GATE_STAGES:
        raise HTTPException(status_code=400, detail=f"unknown gate stage: {request.stage}")
    if request.stage == "hero_gate":
        preflight_errors = _storyboard_preflight_errors(project_id)
        if preflight_errors:
            raise HTTPException(
                status_code=409,
                detail={"message": "分镜安全预检未通过", "errors": preflight_errors},
            )
    if request.stage == "take_gate":
        try:
            _require_selected_playable_takes(project_id, _run_root(project_id))
        except HTTPException:
            raise HTTPException(status_code=409, detail="请先完成每个镜头的真实媒体质检与 Take 选用") from None
    try:
        approved = engine.approve_gate(
            project_id,
            request.stage,
            approver=request.approver,
            notes=request.notes,
            db_path=_db_path(),
            run_root=_run_root(project_id),
        )
        status = engine.run_until_blocked(
            project_id,
            db_path=_db_path(),
            run_root=_run_root(project_id),
            mock=request.mock,
        )
    except checkpoint.GateApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "approved": _engine_status(approved),
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
    }


@app.post("/api/v2/gates/rewrite")
def rewrite_gate(request: GateRewriteRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    if request.stage != "script_gate":
        raise HTTPException(status_code=400, detail="only script_gate can be rewritten")
    root = _run_root(project_id)
    latest_gate = _latest_checkpoint_for_stage(project_id, "script_gate", root)
    if latest_gate is None or latest_gate.get("status") != "awaiting_human":
        raise HTTPException(status_code=409, detail="script_gate is not awaiting human review")

    data = dict(latest_gate.get("data") or {})
    data["rewrite_reason"] = request.reason
    checkpoint.write_checkpoint(
        project_id,
        "script_gate",
        status="needs_review",
        artifacts=dict(latest_gate.get("artifacts") or {}),
        data=data,
        run_root=root,
    )
    queue.enqueue_task(
        project_id=project_id,
        stage="script",
        agent="script",
        task_type="default",
        payload={"run_root": root.as_posix(), "rewrite_reason": request.reason},
        db_path=_db_path(),
    )
    queue.enqueue_task(
        project_id=project_id,
        stage="script_review",
        agent="review",
        task_type="default",
        payload={"run_root": root.as_posix(), "rewrite_reason": request.reason},
        db_path=_db_path(),
    )
    status = engine.run_until_blocked(
        project_id,
        db_path=_db_path(),
        run_root=root,
        mock=request.mock,
    )
    return {"engine": _engine_status(status), "project": _project_summary(project_id)}


@app.post("/api/v2/hero/regen")
def regen_hero(request: HeroRegenRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    if request.shot_index < 1:
        raise HTTPException(status_code=400, detail="shot_index must be >= 1")
    manifest = _load_artifact(project_id, "asset_manifest")
    frame = _find_hero_frame(manifest, request.shot_index)
    frame["status"] = "generated"
    frame["regenerated_at"] = queue.utc_now()
    artifacts.save_artifact(project_id, "asset_manifest", manifest, run_root=_run_root(project_id))
    queue.record_event(
        project_id=project_id,
        event_type="hero.regenerated",
        message=f"shot{request.shot_index}",
        meta={"shot_index": request.shot_index},
        db_path=_db_path(),
    )
    _attach_preview_urls(project_id, manifest)
    return {
        "ok": True,
        "project_id": project_id,
        "shot_index": request.shot_index,
        "asset_manifest": manifest,
    }


@app.post("/api/v2/tasks/retry")
def retry_task(request: TaskRetryRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    try:
        if request.task_id is not None:
            task = queue.get_task(request.task_id, db_path=_db_path())
            if task.project_id != project_id:
                raise ValueError("task does not belong to project")
            queue.requeue_task(request.task_id, db_path=_db_path())
            status = engine.run_until_blocked(
                project_id,
                db_path=_db_path(),
                run_root=_run_root(project_id),
                mock=request.mock,
            )
        elif request.shot_index is not None:
            status = engine.retry_failed_shot(
                project_id,
                request.shot_index,
                db_path=_db_path(),
                run_root=_run_root(project_id),
                mock=request.mock,
            )
        else:
            raise ValueError("task_id or shot_index is required")
        if status.status not in {"awaiting_human", "failed", "blocked", "needs_review", "succeeded"}:
            status = engine.run_until_blocked(
                project_id,
                db_path=_db_path(),
                run_root=_run_root(project_id),
                mock=request.mock,
            )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"engine": _engine_status(status), "project": _project_summary(project_id)}


@app.get("/api/v2/runs/{project_id}/{relative_path:path}", include_in_schema=False)
def get_run_file(project_id: str, relative_path: str) -> FileResponse:
    project_id = _validate_project_id(project_id)
    target = _safe_run_file(_run_root(project_id), relative_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="run file not found")
    return FileResponse(target)


@app.get("/api/v2/download/{project_id}")
def download_project(project_id: str) -> FileResponse:
    project_id = _validate_project_id(project_id)
    zip_path = _build_delivery_zip(project_id)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{project_id}.zip",
    )


@app.post("/api/v2/feedback")
def write_feedback(request: FeedbackRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="feedback text is required")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="feedback text is too long")

    feedback_root = _feedback_root()
    feedback_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path = feedback_root / f"{project_id}-{stamp}-{secrets.token_hex(2)}.json"
    payload = {
        "version": "2.0",
        "project_id": project_id,
        "author": request.author,
        "text": text,
        "created_at": queue.utc_now(),
    }
    _atomic_write_json(path, payload)
    queue.record_event(
        project_id=project_id,
        event_type="feedback.created",
        message=text[:120],
        meta={"path": path.as_posix(), "author": request.author},
        db_path=_db_path(),
    )
    return {"ok": True, "path": str(path), "feedback": payload}


@app.post("/api/v2/review/final-visual")
def approve_final_visual_review(request: FinalVisualReviewRequest) -> dict[str, Any]:
    """Record the mandatory human visual review before final QA can pass."""
    project_id = _validate_project_id(request.project_id)
    root = _run_root(project_id)
    _load_artifact(project_id, "render_report")
    checks = {
        "product_identity": request.product_identity,
        "no_invented_brand": request.no_invented_brand,
        "temperature_display": request.temperature_display,
        "usage_flow": request.usage_flow,
        "person_scene_continuity": request.person_scene_continuity,
    }
    failed = [name for name, passed in checks.items() if not passed]
    review = {
        "version": "2.0",
        "project_id": project_id,
        "artifact_type": "final_visual_review",
        "status": "approved" if not failed else "blocked",
        "checks": checks,
        "reviewer": request.reviewer.strip() or "operator",
        "notes": (request.notes or "").strip(),
        "created_at": queue.utc_now(),
    }
    _atomic_write_json(root / "artifacts" / "final_visual_review.json", review)
    queue.record_event(
        project_id=project_id,
        event_type="final_visual_review.saved",
        message=review["status"],
        meta={"failed_checks": failed},
        db_path=_db_path(),
    )
    if failed:
        raise HTTPException(status_code=409, detail=f"视觉验收未通过：{', '.join(failed)}")

    task_id = queue.enqueue_task(
        project_id=project_id,
        stage="final_qa",
        agent="review",
        payload={"run_root": root.as_posix(), "revision": queue.utc_now()},
        db_path=_db_path(),
    )
    status = engine.run_until_blocked(project_id, db_path=_db_path(), run_root=root, mock=False)
    return {"ok": True, "review": review, "task_id": task_id, "engine": _engine_status(status), "project": _project_summary(project_id)}


def _db_path() -> Path:
    return queue.resolve_db_path()


def _runs_root() -> Path:
    configured = os.environ.get("VAF_RUNS_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return RUNS_ROOT


def _material_library_root() -> Path:
    configured = os.environ.get("VAF_MATERIAL_LIBRARY_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return DATA_ROOT / "01_素材库" / "对标视频" / "manual_import"


def _feedback_root() -> Path:
    configured = os.environ.get("VAF_FEEDBACK_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return DATA_ROOT / "05_反馈库"


def _tool_context(*, mock: bool = True) -> manual_import.ToolContext:
    from tools.base_tool import ToolContext

    return ToolContext.from_mapping(
        {
            "mock": mock,
            "env": os.environ,
        }
    )


def _require_approved_gate(project_id: str, stage: str, root: Path) -> None:
    latest = _latest_checkpoint_for_stage(project_id, stage, root)
    if latest is None or latest.get("status") != "succeeded":
        labels = {"script_gate": "脚本确认", "hero_gate": "关键帧确认"}
        raise HTTPException(status_code=409, detail=f"请先完成{labels.get(stage, stage)}后再运行此节点")


def _is_playable_take_path(root: Path, path_text: str) -> bool:
    if not path_text:
        return False
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return _is_playable_delivery_file(candidate)


def _require_selected_playable_takes(project_id: str, root: Path) -> None:
    plan = _load_artifact(project_id, "shot_plan")
    manifest = _load_artifact(project_id, "take_manifest")
    by_number = {int(item.get("number") or 0): item for item in manifest.get("shots", [])}
    failures: list[str] = []
    for shot in plan.get("shots", []):
        number = int(shot.get("number") or 0)
        entry = by_number.get(number) or {}
        selected_id = entry.get("selected_take_id")
        selected = next((take for take in entry.get("takes", []) if take.get("take_id") == selected_id), None)
        if selected is None or not _is_playable_take_path(root, str(selected.get("path") or "")):
            failures.append(f"镜头 {number}")
    if failures:
        raise HTTPException(status_code=409, detail=f"请先为以下镜头选用可播放 Take：{', '.join(failures)}")


def _storyboard_preflight_errors(project_id: str) -> list[dict[str, Any]]:
    project = _project_summary(project_id)
    shot_plan = _load_artifact(project_id, "shot_plan")
    warming_cup = "\u6052\u6e29\u676f" in str(project.get("product_id") or "")
    errors: list[dict[str, Any]] = []
    for shot in shot_plan.get("shots", []):
        number = int(shot.get("number") or 0)
        prompt = str(shot.get("seedance_prompt") or "")
        lowered = prompt.casefold()
        missing: list[str] = []
        if "white-background hero" not in lowered and "product appearance must match" not in lowered:
            missing.append("产品身份参考")
        if "continuity lock" not in lowered and "same location" not in lowered:
            missing.append("场景与人物连续性")
        if warming_cup:
            if "separate products" not in lowered or "never insert" not in lowered:
                missing.append("恒温杯与奶瓶分离规则")
            if "fahrenheit" not in lowered or "never celsius" not in lowered:
                missing.append("98°F 华氏温标规则")
            if any(token in prompt for token in ("掳F", "Â°F", "锟斤拷F")):
                missing.append("98°F 温标文本编码")
            if number == 4:
                visible_action = " ".join(
                    str(shot.get(key) or "") for key in ("visual", "visual_prompt")
                ).casefold()
                if not all(token in visible_action for token in ("pour", "spout", "baby bottle")):
                    missing.append("第4镜倒液动作一致性")
        if missing:
            errors.append({"shot_index": number, "missing": missing})
    return errors


def _run_root(project_id: str) -> Path:
    row = _project_row_or_none(project_id)
    if row is not None:
        payload = _loads_json(row["payload_json"])
        run_root = payload.get("run_root")
        if run_root:
            return Path(str(run_root))
    return _runs_root() / project_id


def _new_project_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"ref-{stamp}-{secrets.token_hex(3)}"


def _new_standalone_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"scratch-{stamp}-{secrets.token_hex(3)}"


def _validate_project_id(project_id: str) -> str:
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise HTTPException(status_code=400, detail="invalid project_id")
    return project_id


def _validate_artifact_name(artifact_name: str) -> str:
    if artifact_name not in ARTIFACT_NAMES:
        raise HTTPException(status_code=404, detail="artifact is not registered")
    return artifact_name


def _normalize_source_link_id(source_link_id: int | None, link_id: str | int | None) -> int | None:
    value = source_link_id if source_link_id is not None else link_id
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _project_row_or_none(project_id: str):
    with queue.get_conn(_db_path()) as conn:
        return conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()


def _project_summary(project_id: str, *, row: Any | None = None) -> dict[str, Any]:
    row = row or _project_row_or_none(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    root = _run_root(project_id)
    payload = _loads_json(row["payload_json"])
    tasks = queue.list_tasks(project_id=project_id, db_path=_db_path())
    checkpoints = checkpoint.read_all(project_id, run_root=root)
    stages = _stage_statuses(tasks, checkpoints)
    pending_gate = _pending_gate(checkpoints)
    current_stage = _current_stage(stages, checkpoints, pending_gate)
    status = _project_status(stages, pending_gate)
    nodes = _node_statuses(stages)
    delivery_ready = status == "succeeded" and _is_playable_delivery_file(root / "artifacts" / "final-video.mp4")
    if payload.get("source_material_id") or payload.get("source_url"):
        nodes[0]["status"] = "succeeded"
    return {
        "project_id": project_id,
        "standalone": bool(payload.get("standalone")),
        "product_id": row["product_id"],
        "source_link_id": row["source_link_id"],
        "source_material_id": payload.get("source_material_id"),
        "source_url": payload.get("source_url"),
        "status": status,
        "delivery_ready": delivery_ready,
        "current_stage": current_stage,
        "current_gate": pending_gate,
        "budget_cny": float(row["budget_cny"]),
        "budget_mode": row["budget_mode"],
        "cost": cost_tracker.get_project_cost(project_id, db_path=_db_path()),
        "nodes": nodes,
        "stages": stages,
        "tasks": [_task_to_dict(task) for task in tasks],
        "artifacts": _artifact_presence(project_id, root),
        "latest_checkpoint": checkpoints[-1] if checkpoints else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _is_standalone_project(row: Any) -> bool:
    return bool(_loads_json(row["payload_json"]).get("standalone"))


def _load_artifact_from_root(root: Path, artifact_name: str) -> dict[str, Any]:
    path = root / "artifacts" / f"{artifact_name}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{artifact_name} not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"{artifact_name} is unreadable") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail=f"{artifact_name} is invalid")
    return payload


def _with_project_id(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    copied = json.loads(json.dumps(payload, ensure_ascii=False))
    copied["project_id"] = project_id
    return copied


def _analysis_from_script(script: dict[str, Any], project_id: str) -> dict[str, Any]:
    sections = script.get("sections") if isinstance(script.get("sections"), list) else []
    pacing: list[dict[str, Any]] = []
    breakdown: list[dict[str, Any]] = []
    voiceover: list[str] = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        timing = str(section.get("timing") or f"{index * 6}-{(index + 1) * 6}s")
        matched = re.fullmatch(r"(\d+)-(\d+)s", timing)
        start, end = (int(matched.group(1)), int(matched.group(2))) if matched else (index * 6, (index + 1) * 6)
        role = str(section.get("role") or "镜头")
        spoken = str(section.get("voiceover_en") or section.get("voiceover_zh") or "")
        voiceover.append(spoken)
        pacing.append({"start_s": start, "end_s": end, "role": role})
        breakdown.append(
            {
                "number": index + 1,
                "timing": timing,
                "visual": str(section.get("scene_zh") or "产品安全画面"),
                "action": str(section.get("action_zh") or "按脚本完成可见动作"),
                "purpose": role,
                "transition": str(section.get("story_beat_zh") or "自然承接上一镜"),
            }
        )
    return {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": None,
        "material_meta_ref": "promoted standalone script",
        "hook_3s": voiceover[0] if voiceover else "独立脚本已导入，等待人工审核。",
        "structure": [str(item.get("role") or "镜头") for item in sections if isinstance(item, dict)],
        "voiceover_text": " ".join(value for value in voiceover if value),
        "pacing": pacing,
        "keyframes": [],
        "shot_breakdown": breakdown,
        "fingerprint": "promoted-standalone-script",
    }


def _is_playable_delivery_file(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1024:
        return False
    try:
        with path.open("rb") as handle:
            header = handle.read(12)
    except OSError:
        return False
    return len(header) >= 8 and header[4:8] == b"ftyp"


def _run_report(project_id: str) -> dict[str, Any]:
    project = _project_summary(project_id)
    root = _run_root(project_id)
    tasks = queue.list_tasks(project_id=project_id, db_path=_db_path())
    with queue.get_conn(_db_path()) as conn:
        cost_rows = conn.execute(
            "SELECT agent, tool, cost_cny, meta_json, created_at FROM cost_entries WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
    task_rows = [
        {
            "task_id": task.id,
            "stage": task.stage,
            "agent": task.agent,
            "status": task.status,
            "attempt": task.attempt,
            "duration_s": _duration_seconds(task.started_at, task.finished_at),
            "error": _redact(task.error_json),
        }
        for task in tasks
    ]
    providers = [
        {
            "agent": row["agent"],
            "tool": row["tool"],
            "cost_cny": float(row["cost_cny"]),
            "meta": _redact(cost_tracker.loads_meta(row["meta_json"])),
            "created_at": row["created_at"],
        }
        for row in cost_rows
    ]
    render = _load_artifact_or_none(project_id, "render_report")
    qa = _load_artifact_or_none(project_id, "qa_report")
    started = min((task.started_at for task in tasks if task.started_at), default=None)
    finished = max((task.finished_at for task in tasks if task.finished_at), default=None)
    return {
        "version": "2.0",
        "project_id": project_id,
        "product_id": project["product_id"],
        "status": project["status"],
        "current_stage": project["current_stage"],
        "source_material_id": project["source_material_id"],
        "started_at": started,
        "finished_at": finished,
        "elapsed_s": _duration_seconds(started, finished),
        "budget_mode": project["budget_mode"],
        "pricing_calibrated": False,
        "cost": project["cost"],
        "tasks": task_rows,
        "providers": providers,
        "failures": [item for item in task_rows if item["error"]],
        "render_report": render,
        "qa_report": qa,
        "artifacts": project["artifacts"],
        "run_root": root.as_posix(),
    }


def _duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round(max(0.0, (finished - started).total_seconds()), 3)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if any(part in str(key).casefold() for part in ("key", "token", "auth")) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _stage_statuses(tasks: list[queue.Task], checkpoints: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest_checkpoints: dict[str, dict[str, Any]] = {}
    for item in checkpoints:
        latest_checkpoints[str(item["stage"])] = item

    result: dict[str, dict[str, Any]] = {}
    for stage in checkpoint.STAGE_ORDER:
        stage_tasks = [task for task in tasks if task.stage == stage]
        task_status = _aggregate_status([task.status for task in stage_tasks])
        checkpoint_status = latest_checkpoints.get(stage, {}).get("status")
        status = str(checkpoint_status) if checkpoint_status else task_status
        result[stage] = {
            "status": status,
            "task_count": len(stage_tasks),
            "errors": [
                {
                    "task_id": task.id,
                    "stage": task.stage,
                    "agent": task.agent,
                    "shot_index": task.payload_json.get("shot_index"),
                    "error_json": task.error_json,
                }
                for task in stage_tasks
                if task.error_json
            ],
        }
    return result


def _node_statuses(stages: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for agent, stage_names in NODE_STAGES.items():
        statuses = [stages[stage]["status"] for stage in stage_names]
        status = _aggregate_status(statuses)
        nodes.append(
            {
                "agent": agent,
                "status": status,
                "stages": list(stage_names),
            }
        )
    return nodes


def _aggregate_status(statuses: list[str]) -> str:
    values = [status for status in statuses if status and status != "idle"]
    if not values:
        return "idle"
    for status in STATUS_PRIORITY:
        if status in values:
            return status
    return values[0]


def _pending_gate(checkpoints: list[dict[str, Any]]) -> str | None:
    latest_by_stage: dict[str, dict[str, Any]] = {}
    for item in checkpoints:
        latest_by_stage[str(item["stage"])] = item
    for stage in reversed(GATE_STAGES):
        if latest_by_stage.get(stage, {}).get("status") == "awaiting_human":
            return stage
    return None


def _current_stage(
    stages: dict[str, dict[str, Any]],
    checkpoints: list[dict[str, Any]],
    pending_gate: str | None,
) -> str | None:
    if pending_gate:
        return pending_gate
    if stages.get("archive", {}).get("status") == "succeeded":
        return "archive"
    for stage, item in stages.items():
        if item["status"] in {"failed", "blocked", "needs_review"}:
            return stage
    for stage in checkpoint.STAGE_ORDER:
        if stages[stage]["status"] in {"running", "queued"}:
            return stage
    if checkpoints:
        return str(checkpoints[-1]["stage"])
    return None


def _source_material_or_none(material_id: str | None) -> dict[str, Any] | None:
    if not material_id:
        return None
    try:
        return manual_import.load_material_meta(material_id, _material_library_root())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _project_status(stages: dict[str, dict[str, Any]], pending_gate: str | None) -> str:
    if pending_gate:
        return "awaiting_human"
    if stages["archive"]["status"] == "succeeded":
        return "succeeded"
    status = _aggregate_status([item["status"] for item in stages.values()])
    return "running" if status in {"queued", "running"} else status


def _artifact_presence(project_id: str, run_root: Path) -> dict[str, bool]:
    artifact_dir = run_root / "artifacts"
    return {
        name: (artifact_dir / f"{name}.json").is_file()
        for name in sorted(ARTIFACT_NAMES)
    }


def _task_to_dict(task: queue.Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "stage": task.stage,
        "agent": task.agent,
        "task_type": task.task_type,
        "status": task.status,
        "attempt": task.attempt,
        "max_retries": task.max_retries,
        "payload_json": task.payload_json,
        "error_json": task.error_json,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "finished_at": task.finished_at,
    }


def _engine_status(status: engine.EngineRunStatus) -> dict[str, Any]:
    return {
        "project_id": status.project_id,
        "stage": status.stage,
        "status": status.status,
        "message": status.message,
    }


def _load_artifact(project_id: str, artifact_name: str) -> dict[str, Any]:
    path = _artifact_path(project_id, artifact_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{artifact_name} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_artifact_or_none(project_id: str, artifact_name: str) -> dict[str, Any] | None:
    path = _artifact_path(project_id, artifact_name)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_path(project_id: str, artifact_name: str) -> Path:
    return _run_root(project_id) / "artifacts" / f"{artifact_name}.json"


def _changed_script_sections(
    old_payload: dict[str, Any] | None,
    new_payload: dict[str, Any],
) -> list[int]:
    if old_payload is None:
        return [int(section["number"]) for section in new_payload.get("sections", [])]
    old_by_number = {
        int(section["number"]): section
        for section in old_payload.get("sections", [])
        if "number" in section
    }
    changed: list[int] = []
    for section in new_payload.get("sections", []):
        number = int(section["number"])
        old_section = old_by_number.get(number)
        if old_section is None:
            changed.append(number)
            continue
        if (
            old_section.get("voiceover_en") != section.get("voiceover_en")
            or old_section.get("timing") != section.get("timing")
        ):
            changed.append(number)
    return changed


def _changed_shots(
    old_payload: dict[str, Any] | None,
    new_payload: dict[str, Any],
) -> list[int]:
    if old_payload is None:
        return [int(shot["number"]) for shot in new_payload.get("shots", [])]
    old_by_number = {
        int(shot["number"]): shot
        for shot in old_payload.get("shots", [])
        if "number" in shot
    }
    return [
        int(shot["number"])
        for shot in new_payload.get("shots", [])
        if old_by_number.get(int(shot["number"])) != shot
    ]


def _refresh_script_gate_checkpoint(project_id: str, stale_sections: list[int]) -> None:
    root = _run_root(project_id)
    latest_gate = _latest_checkpoint_for_stage(project_id, "script_gate", root)
    if latest_gate is None or latest_gate.get("status") != "awaiting_human":
        return
    artifact_refs = dict(latest_gate.get("artifacts") or {})
    artifact_refs["script_copy"] = "artifacts/script_copy.json"
    if (root / "artifacts" / "review_report.json").is_file():
        artifact_refs["review_report"] = "artifacts/review_report.json"
    data = dict(latest_gate.get("data") or {})
    data["stale_sections"] = stale_sections
    checkpoint.write_checkpoint(
        project_id,
        "script_gate",
        status="awaiting_human",
        artifacts=artifact_refs,
        data=data,
        run_root=root,
    )


def _latest_checkpoint_for_stage(project_id: str, stage: str, run_root: Path) -> dict[str, Any] | None:
    for item in reversed(checkpoint.read_all(project_id, run_root=run_root)):
        if item.get("stage") == stage:
            return item
    return None


def _find_hero_frame(manifest: dict[str, Any], shot_index: int) -> dict[str, Any]:
    for frame in manifest.get("hero_frames", []):
        if int(frame.get("number", 0)) == shot_index:
            return frame
    raise HTTPException(status_code=404, detail=f"hero frame not found for shot {shot_index}")


def _attach_preview_urls(project_id: str, manifest: dict[str, Any]) -> None:
    run_root = _run_root(project_id)
    for frame in manifest.get("hero_frames", []):
        path_text = str(frame.get("path") or "")
        path = Path(path_text)
        try:
            relative = path.resolve().relative_to(run_root.resolve()).as_posix()
        except ValueError:
            relative = f"shots/{path.name}"
        frame["preview_url"] = f"/api/v2/runs/{project_id}/{relative}"


def _attach_take_media_status(project_id: str, manifest: dict[str, Any]) -> None:
    root = _run_root(project_id).resolve()
    for shot in manifest.get("shots", []):
        for take in shot.get("takes", []):
            path_text = str(take.get("path") or "").replace("\\", "/")
            try:
                candidate = Path(path_text).resolve()
                relative = candidate.relative_to(root).as_posix()
            except ValueError:
                relative = f"shots/{Path(path_text).name}"
                candidate = root / relative
            playable = _is_playable_delivery_file(candidate)
            take["playable"] = playable
            take["media_url"] = f"/api/v2/runs/{project_id}/{relative}" if playable else ""
            take["media_message"] = "媒体已就绪" if playable else "无可播放视频：请以真实运行模式重新生成此 Take。"


def _safe_run_file(run_root: Path, relative_path: str) -> Path:
    candidate = (run_root / relative_path).resolve()
    try:
        candidate.relative_to(run_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid run file path") from exc
    return candidate


def _build_delivery_zip(project_id: str) -> Path:
    run_root = _run_root(project_id)
    if not run_root.exists():
        raise HTTPException(status_code=404, detail="run not found")
    delivery_dir = run_root / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(delivery_dir / "run_report.json", _run_report(project_id))
    zip_path = delivery_dir / f"{project_id}.zip"
    files = [
        path
        for path in run_root.rglob("*")
        if path.is_file() and path.resolve() != zip_path.resolve()
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(run_root).as_posix())
    return zip_path


def _load_product_library(*, refresh: bool = False) -> dict[str, Any]:
    return product_library.refresh_index() if refresh else product_library.load_index(refresh_if_missing=True)


def _list_products(index: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    products = (index or {}).get("products", [])
    if products:
        return sorted((_product_option(item) for item in products), key=lambda item: (not item["ready"], item["label"]))

    materials_root = DATA_ROOT / "01_素材库" / "产品资料"
    items: list[dict[str, Any]] = []
    if materials_root.exists():
        for product_doc in sorted(materials_root.glob("*.md")):
            product_id = product_doc.stem
            product_dir = materials_root / product_id
            has_white_hero = bool(list(product_dir.rglob("白底主图.*"))) if product_dir.exists() else False
            items.append(
                {
                    "id": product_id,
                    "label": product_id,
                    "ready": has_white_hero,
                    "seedance_source": "",
                    "issue_count": 0 if has_white_hero else 1,
                    "issues": [],
                    "counts": {},
                    "ds223_refreshed": False,
                }
            )
    if not items:
        items.append(
            {
                "id": "便携恒温杯",
                "label": "便携恒温杯",
                "ready": True,
                "seedance_source": "",
                "issue_count": 0,
                "issues": [],
                "counts": {},
                "ds223_refreshed": False,
            }
        )
    return sorted(items, key=lambda item: (not item["ready"], item["label"]))


def _product_option(product: dict[str, Any]) -> dict[str, Any]:
    issues = list(product.get("issues") or [])
    return {
        "id": product.get("id"),
        "label": product.get("label") or product.get("id"),
        "ready": bool(product.get("ready")),
        "seedance_source": product.get("seedance_source") or "",
        "issue_count": len(issues),
        "issues": issues,
        "counts": product.get("counts") or {},
        "ds223_refreshed": bool(product.get("ds223_refreshed")),
    }


def _loads_json(value: str | bytes | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
