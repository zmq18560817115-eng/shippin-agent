from __future__ import annotations

import os
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.base_tool import ToolContext
from tools.providers import ark


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


def inspect_review_frames(
    frame_paths: list[str],
    *,
    product_id: str = "",
    shot: dict[str, Any] | None = None,
    context: ToolContext | None = None,
) -> dict[str, Any]:
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
    report = {
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
    if shot and context and not context.mock and frame_paths:
        semantic = _inspect_semantics(frame_paths, shot=shot, product_id=product_id, context=context)
        report["semantic_visual_qa"] = semantic
        report["checks"].update(
            {
                "product_structure_match": semantic["checks"]["product_structure_match"],
                "target_container_match": semantic["checks"]["target_container_match"],
                "pour_direction_match": semantic["checks"]["pour_direction_match"],
                "display_screen_off": semantic["checks"]["display_screen_off"],
                "no_unwanted_pour": semantic["checks"]["no_unwanted_pour"],
                "main_lid_closed": semantic["checks"]["main_lid_closed"],
                "spout_only_pour": semantic["checks"]["spout_only_pour"],
            }
        )
        if semantic["status"] == "BLOCKED":
            report["status"] = "BLOCKED"
            report["summary"] = semantic["summary"]
        elif semantic["status"] == "NEEDS_REVIEW" and report["status"] == "PASS":
            report["status"] = "NEEDS_REVIEW"
            report["summary"] = f"{report['summary']} {semantic['summary']}"
    return report


def _inspect_semantics(
    frame_paths: list[str],
    *,
    shot: dict[str, Any],
    product_id: str,
    context: ToolContext,
) -> dict[str, Any]:
    number = int(shot.get("number") or 0)
    pouring_shot = number == 4
    prompt = (
        "你是严格的视频产品质检员。只根据抽帧中清晰可见的事实判断，不得猜测。"
        f"产品为{product_id or '待验收产品'}，必须与参考产品保持相同主体结构、杯盖、把手、出液口和控制区域。"
        + (
            "这是倒液镜头：恒温杯主盖必须关闭，液体只能从圆形出液口流出，方向必须是恒温杯到一个独立、透明、无品牌、"
            "具有奶嘴或螺纹颈/刻度等奶瓶结构证据的婴儿奶瓶。玻璃杯、罐子、马克杯和普通水杯均不合格。"
            if pouring_shot
            else "本镜头不应出现倒液动作；显示屏应熄灭、不可读或避开画面。"
        )
        + (
            "判定 main_lid_closed 时，只要带螺纹的主盖总成仍完整安装并锁紧在杯身上即可；"
            "为露出圆形出液口而打开外层小防尘盖是允许的，不得把小防尘盖误判成主盖。"
            "spout_only_pour 仅在液体从主盖总成上的圆形小出液口流出时为 true；"
            "若从杯身大口径主开口流出则为 false。"
            if pouring_shot
            else ""
        )
        + "输出 JSON，字段必须为 product_structure_match、target_container_match、pour_direction_match、"
        "display_screen_off、no_unwanted_pour、main_lid_closed、spout_only_pour 七个布尔值，"
        "以及 evidence_zh（简短中文证据）和 uncertain（布尔值）。看不清时 uncertain=true 且相关布尔值=false。"
    )
    try:
        result, provider = ark.vision_json(context, prompt=prompt, image_paths=frame_paths)
    except Exception as exc:
        return {
            "status": "NEEDS_REVIEW",
            "engine": "not_available",
            "checks": {
                "product_structure_match": False,
                "target_container_match": not pouring_shot,
                "pour_direction_match": not pouring_shot,
                "display_screen_off": False,
                "no_unwanted_pour": False,
                "main_lid_closed": not pouring_shot,
                "spout_only_pour": not pouring_shot,
            },
            "summary": f"自动容器视觉检查不可用，必须人工复核：{str(exc)[:180]}",
            "evidence_zh": "",
        }
    checks = {
        "product_structure_match": result.get("product_structure_match") is True,
        "target_container_match": result.get("target_container_match") is True if pouring_shot else True,
        "pour_direction_match": result.get("pour_direction_match") is True if pouring_shot else True,
        "display_screen_off": True if pouring_shot else result.get("display_screen_off") is True,
        "no_unwanted_pour": True if pouring_shot else result.get("no_unwanted_pour") is True,
        "main_lid_closed": result.get("main_lid_closed") is True if pouring_shot else True,
        "spout_only_pour": result.get("spout_only_pour") is True if pouring_shot else True,
    }
    uncertain = result.get("uncertain") is True
    passed = all(checks.values()) and not uncertain
    return {
        "status": "PASS" if passed else "BLOCKED",
        "engine": provider.get("model") or "ark-vision",
        "checks": checks,
        "summary": "产品结构、目标容器和动作方向检查通过。" if passed else "产品结构、目标容器或倒液方向未通过自动视觉检查。",
        "evidence_zh": str(result.get("evidence_zh") or "")[:500],
        "uncertain": uncertain,
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
