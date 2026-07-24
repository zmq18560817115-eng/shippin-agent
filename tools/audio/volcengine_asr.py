from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx

from tools.base_tool import ToolContext, ToolResult
from tools.tool_registry import register_tool


FLASH_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
RESOURCE_ID = "volc.bigasr.auc_turbo"


@register_tool("volcengine_asr")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    supplied = str(payload.get("transcript_text") or "").strip()
    if context.mock:
        transcript = supplied or "夜间准备奶液时，清晰展示正确的产品使用流程。"
        return ToolResult.success(
            {
                "transcript_text": transcript,
                "segments": [{"start_s": 0.0, "end_s": 5.0, "text": transcript}],
            },
            meta={"tool": "volcengine_asr", "mock": True, "audio_path": payload.get("audio_path")},
        )
    if supplied:
        return ToolResult.success(
            {
                "transcript_text": supplied,
                "segments": [{"start_s": 0.0, "end_s": 0.0, "text": supplied}],
            },
            meta={"tool": "volcengine_asr", "mock": False, "source": "operator"},
        )

    source = Path(str(payload.get("audio_path") or ""))
    if not source.is_file():
        return ToolResult.failure("validation", "ASR 需要存在的音频或视频文件")
    api_key = str(context.env.get("VOLCENGINE_ASR_API_KEY") or "").strip()
    app_key = str(context.env.get("VOLCENGINE_ASR_APP_KEY") or "").strip()
    access_key = str(context.env.get("VOLCENGINE_ASR_ACCESS_KEY") or "").strip()
    local_enabled = str(context.env.get("VAF_LOCAL_ASR_ENABLED") or "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not api_key and not (app_key and access_key) and local_enabled:
        return _execute_local(source, context)
    if not api_key and not (app_key and access_key):
        return ToolResult.failure(
            "not_configured",
            "未配置语音识别：填写 VOLCENGINE_ASR_API_KEY，或启用本地 Faster-Whisper",
        )

    try:
        audio_path, temporary = _ensure_supported_audio(source)
        try:
            if audio_path.stat().st_size > 100 * 1024 * 1024:
                return ToolResult.failure("validation", "ASR 音频超过 100MB，请先切片")
            response = _recognize(
                audio_path,
                api_key=api_key,
                app_key=app_key,
                access_key=access_key,
            )
        finally:
            if temporary:
                audio_path.unlink(missing_ok=True)
    except (OSError, subprocess.SubprocessError, httpx.HTTPError, ValueError) as exc:
        return ToolResult.failure("provider", f"语音识别失败：{exc}")

    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    text = str(result.get("text") or response.get("text") or "").strip()
    if not text:
        return ToolResult.failure("provider", "语音识别调用成功，但结果中没有转写文本")
    utterances = result.get("utterances") or response.get("utterances") or []
    segments = [
        _segment(item)
        for item in utterances
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    if not segments:
        segments = [{"start_s": 0.0, "end_s": 0.0, "text": text}]
    return ToolResult.success(
        {"transcript_text": text, "segments": segments},
        meta={
            "tool": "volcengine_asr",
            "mock": False,
            "source": "volcengine_flash",
            "segment_count": len(segments),
        },
    )


def _execute_local(source: Path, context: ToolContext) -> ToolResult:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return ToolResult.failure(
            "not_configured",
            "本地 ASR 已启用但 faster-whisper 未安装，请安装 requirements-local-asr.txt",
        )
    model_name = str(context.env.get("VAF_LOCAL_ASR_MODEL") or "base").strip()
    device = str(context.env.get("VAF_LOCAL_ASR_DEVICE") or "cpu").strip()
    compute_type = str(
        context.env.get("VAF_LOCAL_ASR_COMPUTE_TYPE") or ("int8" if device == "cpu" else "float16")
    ).strip()
    cache_dir = str(context.env.get("VAF_LOCAL_ASR_CACHE_DIR") or "").strip() or None
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type, download_root=cache_dir)
        segments_iter, info = model.transcribe(
            source.as_posix(),
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True,
        )
        segments = [
            {
                "start_s": round(float(segment.start), 3),
                "end_s": round(float(segment.end), 3),
                "text": str(segment.text).strip(),
            }
            for segment in segments_iter
            if str(segment.text).strip()
        ]
    except Exception as exc:
        return ToolResult.failure("provider", f"本地语音识别失败：{exc}")
    text = " ".join(segment["text"] for segment in segments).strip()
    if not text:
        return ToolResult.failure("provider", "本地语音识别完成，但没有识别出有效语音")
    return ToolResult.success(
        {"transcript_text": text, "segments": segments},
        meta={
            "tool": "volcengine_asr",
            "mock": False,
            "source": "faster_whisper",
            "model": model_name,
            "language": getattr(info, "language", None),
            "segment_count": len(segments),
        },
    )


def _recognize(
    audio_path: Path,
    *,
    api_key: str,
    app_key: str,
    access_key: str,
) -> dict[str, Any]:
    headers = {
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["X-Api-Key"] = api_key
    else:
        headers["X-Api-App-Key"] = app_key
        headers["X-Api-Access-Key"] = access_key
    body = {
        "user": {"uid": "video-agent-factory"},
        "audio": {
            "format": audio_path.suffix.lstrip(".").casefold(),
            "data": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "show_utterances": True,
        },
    }
    response = httpx.post(FLASH_URL, headers=headers, json=body, timeout=120.0)
    response.raise_for_status()
    status = response.headers.get("X-Api-Status-Code")
    payload = response.json()
    if status and status != "20000000":
        raise ValueError(response.headers.get("X-Api-Message") or f"供应商状态码 {status}")
    return payload


def _ensure_supported_audio(source: Path) -> tuple[Path, bool]:
    if source.suffix.casefold() in {".wav", ".mp3", ".ogg", ".opus"}:
        return source, False
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, RuntimeError):
            ffmpeg = None
    if not ffmpeg:
        raise OSError("未找到 FFmpeg，无法从视频提取音轨")
    target = Path(tempfile.gettempdir()) / f"vaf-asr-{uuid.uuid4().hex}.mp3"
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            source.as_posix(),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            "-y",
            target.as_posix(),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0 or not target.is_file():
        raise OSError(completed.stderr.strip() or "音轨提取失败")
    return target, True


def _segment(item: dict[str, Any]) -> dict[str, Any]:
    start = item.get("start_time") if item.get("start_time") is not None else item.get("start_ms", 0)
    end = item.get("end_time") if item.get("end_time") is not None else item.get("end_ms", 0)
    return {
        "start_s": round(float(start or 0) / 1000, 3),
        "end_s": round(float(end or 0) / 1000, 3),
        "text": str(item.get("text") or "").strip(),
    }
