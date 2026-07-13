from __future__ import annotations

import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx

from libshared.paths import ROOT
from tools.base_tool import ToolContext, ToolNotConfiguredError


CHAT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_DOUBAO_MODEL = "doubao-seed-1-8-251228"
DEFAULT_SEEDANCE_MODEL = "doubao-seedance-2-0-fast-260128"


class ArkProviderError(RuntimeError):
    category = "provider_error"


def env_value(context: ToolContext, *names: str) -> str:
    for name in names:
        value = str(context.env.get(name, "")).strip()
        if value:
            return value
    raise ToolNotConfiguredError(f"missing environment variables: {', '.join(names)}")


def chat_json(
    context: ToolContext,
    *,
    api_key_names: Iterable[str],
    messages: list[dict[str, str]],
    model_env: str = "DOUBAO_MODEL",
    default_model: str = DEFAULT_DOUBAO_MODEL,
    temperature: float = 0.3,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = env_value(context, *api_key_names)
    model = str(context.env.get(model_env) or context.env.get("ARK_DOUBAO_MODEL") or default_model).strip()
    timeout_s = float(context.env.get("ARK_TIMEOUT_S") or 120)
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    payload = _post_json(
        _chat_base_url(context) + "/chat/completions",
        api_key=api_key,
        body=body,
        timeout_s=timeout_s,
    )
    content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise ArkProviderError("Ark chat response did not contain message content")
    return _json_from_text(content), {
        "provider": "ark",
        "model": model,
        "usage": payload.get("usage") or {},
        "response_id": payload.get("id"),
    }


def create_seedance_video(
    context: ToolContext,
    *,
    prompt: str,
    image_path: str,
    output_path: Path,
    duration_sec: int = 5,
    aspect_ratio: str = "9:16",
) -> dict[str, Any]:
    api_key = env_value(context, "SEEDANCE_API_KEY", "ARK_SEEDANCE_API_KEY", "ARK_API_KEY")
    model = str(context.env.get("SEEDANCE_MODEL") or context.env.get("ARK_SEEDANCE_MODEL") or DEFAULT_SEEDANCE_MODEL).strip()
    resolution = str(context.env.get("SEEDANCE_RESOLUTION") or "1080p").strip()
    base_url = _chat_base_url(context)
    timeout_s = float(context.env.get("ARK_TIMEOUT_S") or 120)
    poll_s = float(context.env.get("SEEDANCE_POLL_INTERVAL_S") or 5)
    max_wait_s = float(context.env.get("SEEDANCE_MAX_WAIT_S") or 900)
    source_path = _resolve_path(image_path)
    body = {
        "model": model,
        "content": [
            {"type": "text", "text": _seedance_prompt(prompt, duration_sec, aspect_ratio)},
            {"type": "image_url", "image_url": {"url": _image_data_url(source_path)}},
        ],
        "ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration_sec,
    }
    created = _post_json(
        base_url + "/contents/generations/tasks",
        api_key=api_key,
        body=body,
        timeout_s=timeout_s,
    )
    task_id = _task_id(created)
    if not task_id:
        raise ArkProviderError(f"Seedance task response missing task id: {_safe_payload(created)}")

    deadline = time.monotonic() + max_wait_s
    last_payload: dict[str, Any] = created
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        last_payload = _get_json(
            base_url + f"/contents/generations/tasks/{task_id}",
            api_key=api_key,
            timeout_s=timeout_s,
        )
        status = _task_status(last_payload)
        if status in {"succeeded", "success", "completed", "done"}:
            video_url = _find_video_url(last_payload)
            if not video_url:
                raise ArkProviderError(f"Seedance completed without video url: {_safe_payload(last_payload)}")
            _download(video_url, output_path, timeout_s=max(timeout_s, 300))
            return {
                "provider": "ark",
                "model": model,
                "task_id": task_id,
                "status": status,
                "video_url": video_url,
            }
        if status in {"failed", "error", "cancelled", "canceled"}:
            raise ArkProviderError(f"Seedance task failed: {_safe_payload(last_payload)}")
    raise ArkProviderError(f"Seedance task timed out after {int(max_wait_s)}s: {_safe_payload(last_payload)}")


def _chat_base_url(context: ToolContext) -> str:
    return str(context.env.get("ARK_BASE_URL") or context.env.get("DOUBAO_BASE_URL") or CHAT_BASE_URL).rstrip("/")


def _post_json(url: str, *, api_key: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    with httpx.Client(timeout=timeout_s, trust_env=False) as client:
        response = client.post(url, headers=_headers(api_key), json=body)
    return _response_json(response)


def _get_json(url: str, *, api_key: str, timeout_s: float) -> dict[str, Any]:
    with httpx.Client(timeout=timeout_s, trust_env=False) as client:
        response = client.get(url, headers=_headers(api_key))
    return _response_json(response)


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ArkProviderError(f"Ark HTTP {response.status_code}: {response.text[:500]}") from exc
    if response.status_code >= 400:
        raise ArkProviderError(f"Ark HTTP {response.status_code}: {_safe_payload(payload)}")
    if not isinstance(payload, dict):
        raise ArkProviderError("Ark response is not a JSON object")
    return payload


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _json_from_text(text: str) -> dict[str, Any]:
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ArkProviderError("Ark chat response was not JSON")
        loaded = json.loads(text[start : end + 1])
    if not isinstance(loaded, dict):
        raise ArkProviderError("Ark chat JSON response was not an object")
    return loaded


def _seedance_prompt(prompt: str, duration_sec: int, aspect_ratio: str) -> str:
    orientation = {"9:16": "vertical", "16:9": "horizontal", "1:1": "square"}.get(aspect_ratio, "vertical")
    return (
        f"{prompt}\n"
        "Use the provided product image as the strict product identity reference. "
        "Do not invent product shape, logo, display, lid, spout, or accessories. "
        f"Duration {duration_sec} seconds, {orientation} {aspect_ratio}, product-safe commercial short video shot."
    )


def _image_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def _task_id(payload: Mapping[str, Any]) -> str:
    for key in ("id", "task_id", "taskId"):
        value = payload.get(key)
        if value:
            return str(value)
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _task_id(data)
    task = payload.get("task")
    if isinstance(task, Mapping):
        return _task_id(task)
    return ""


def _task_status(payload: Mapping[str, Any]) -> str:
    for key in ("status", "state"):
        value = payload.get(key)
        if value:
            return str(value).strip().casefold()
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _task_status(data)
    task = payload.get("task")
    if isinstance(task, Mapping):
        return _task_status(task)
    return ""


def _find_video_url(value: Any) -> str:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).casefold()
            if key_text in {"video_url", "videourl", "url", "source_url"} and isinstance(item, str):
                if item.startswith("http") and _looks_like_video_url(item):
                    return item
            found = _find_video_url(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_video_url(item)
            if found:
                return found
    return ""


def _looks_like_video_url(url: str) -> bool:
    lowered = url.casefold()
    return ".mp4" in lowered or ".mov" in lowered or "video" in lowered or "tos-" in lowered


def _download(url: str, output_path: Path, *, timeout_s: float) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=timeout_s, follow_redirects=True, trust_env=False) as client:
        response = client.get(url)
    if response.status_code >= 400:
        raise ArkProviderError(f"download HTTP {response.status_code}")
    output_path.write_bytes(response.content)
    if output_path.stat().st_size <= 0:
        raise ArkProviderError("downloaded video file is empty")


def _safe_payload(payload: Any) -> str:
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        text = str(payload)
    return text[:1200]
