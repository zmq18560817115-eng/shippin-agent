from __future__ import annotations

import os
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


VALID_FAHRENHEIT = re.compile(r"(?<!\d)98\s*(?:°\s*)?F\b", re.IGNORECASE)
FORBIDDEN_CELSIUS = re.compile(r"(?<!\d)98\s*(?:°\s*)?(?:C|℃)\b", re.IGNORECASE)


def resolve_tesseract() -> str | None:
    configured = os.environ.get("VAF_TESSERACT_CMD", "").strip().strip('"')
    if configured and Path(configured).is_file():
        return str(Path(configured))
    discovered = shutil.which("tesseract")
    if discovered:
        return discovered
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def resolve_ffmpeg() -> str | None:
    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered
    try:
        import imageio_ffmpeg

        executable = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None
    return executable if executable and Path(executable).is_file() else None


def inspect_review_frames(frame_paths: list[str], *, product_id: str = "") -> dict[str, Any]:
    """Run deterministic OCR checks without replacing mandatory human review."""
    executable = resolve_tesseract()
    rapidocr_ready = importlib.util.find_spec("rapidocr_onnxruntime") is not None
    warming_product = any(
        token in product_id.casefold()
        for token in ("恒温杯", "温奶", "bottle warmer", "warming cup")
    )
    frames: list[dict[str, Any]] = []
    for path_text in frame_paths:
        path = Path(path_text)
        text = ""
        if path.is_file():
            if executable:
                text = _ocr_frame(path, executable)
            elif rapidocr_ready:
                text = _rapidocr_frame(path)
        frames.append(
            {
                "path": path.as_posix(),
                "ocr_text": text[:500],
                "valid_98f": bool(VALID_FAHRENHEIT.search(text)),
                "forbidden_98c": bool(FORBIDDEN_CELSIUS.search(text)),
            }
        )
    forbidden = [item["path"] for item in frames if item["forbidden_98c"]]
    valid = [item["path"] for item in frames if item["valid_98f"]]
    if forbidden:
        status, summary = "BLOCKED", "OCR 识别到禁止的 98°C/摄氏温标，必须重做对应镜头。"
    elif not warming_product:
        status, summary = "PASS", "当前产品不启用恒温杯温标规则；仍需人工检查产品身份和动作连续性。"
    elif not executable and not rapidocr_ready:
        status, summary = "NEEDS_REVIEW", "未配置 OCR 引擎，温标由人工终审确认。"
    elif valid:
        status, summary = "PASS", "OCR 至少在一张抽帧中识别到 98°F；仍需人工确认字形和产品外观。"
    else:
        status, summary = "NEEDS_REVIEW", "OCR 未识别到明确温标；可能是屏幕未点亮或字形不可读，必须人工复核。"
    return {
        "version": "1.0",
        "status": status,
        "engine": "tesseract" if executable else ("rapidocr" if rapidocr_ready else "not_configured"),
        "checks": {
            "no_forbidden_celsius": not forbidden,
            "valid_98f_detected": bool(valid),
            "frames_sampled": len(frames),
        },
        "summary": summary,
        "frames": frames,
    }


def extract_review_frames(
    video_path: str | Path,
    output_dir: str | Path,
    *,
    limit: int = 3,
) -> list[Path]:
    """Extract a small deterministic sample for per-Take visual review."""
    ffmpeg = resolve_ffmpeg()
    source = Path(video_path)
    target = Path(output_dir)
    if not ffmpeg or not source.is_file() or limit < 1:
        return []
    target.mkdir(parents=True, exist_ok=True)
    pattern = target / "frame-%02d.jpg"
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                source.as_posix(),
                "-vf",
                "fps=1/2,scale=720:-2",
                "-frames:v",
                str(limit),
                pattern.as_posix(),
            ],
            capture_output=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return sorted(target.glob("frame-*.jpg"))[:limit]


def _ocr_frame(path: Path, executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, path.as_posix(), "stdout", "--psm", "11", "-l", "eng"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _rapidocr_frame(path: Path) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR

        result, _ = RapidOCR()(path.as_posix())
    except Exception:
        return ""
    if not result:
        return ""
    return " ".join(str(item[1]) for item in result if len(item) > 1).strip()
