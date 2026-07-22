from __future__ import annotations

import hashlib
import re
from typing import Any

from libshared import artifacts
from libshared.agent_contracts import agent_system_prompt
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


@register_tool("doubao_analyze")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
        return _execute_real(payload, context)
    project_id = str(payload.get("project_id") or "ref-mock")
    transcript = str(payload.get("transcript_text") or "")
    hook = _mock_hook(transcript)
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "material_meta_ref": str(payload.get("source_material_id") or payload.get("source_url") or ""),
        "hook_3s": hook,
        "structure": ["钩子", "痛点", "方案", "证明", "行动号召"],
        "voiceover_text": transcript or "便携恒温杯夜间喂养准备的演练素材转写。",
        "pacing": [
            {"start_s": 0, "end_s": 6, "role": "钩子"},
            {"start_s": 6, "end_s": 12, "role": "痛点"},
            {"start_s": 12, "end_s": 18, "role": "方案"},
            {"start_s": 18, "end_s": 24, "role": "证明"},
            {"start_s": 24, "end_s": 30, "role": "行动号召"},
        ],
        "keyframes": [],
        "shot_breakdown": _fallback_shot_breakdown(),
        "fingerprint": f"mock-analysis-{hashlib.sha256(transcript.encode('utf-8')).hexdigest()[:10]}",
    }
    artifacts.validate_artifact("analysis_report", report)
    return ToolResult.success(
        {"analysis_report": report},
        cost_cny=context.pricing_for("doubao_analyze") if not context.mock else 0.0,
        meta={"tool": "doubao_analyze", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _mock_hook(transcript: str) -> str:
    if any(token in transcript for token in ("旅行", "旅途", "出行", "机场", "高铁", "酒店")):
        return "登车时间在变，喂养准备别再临时找办法。"
    if any(token in transcript for token in ("办公室", "办公", "通勤", "工位", "午休")):
        return "午休只剩十分钟，准备动作不能再绕远。"
    if any(token in transcript for token in ("露营", "户外", "公园", "野餐")):
        return "户外空间有限，准备顺序更要清楚。"
    return "夜间喂养准备，也可以更轻松。"


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    transcript = str(payload.get("transcript_text") or payload.get("source_url") or "Manual competitor link intake.")
    duration_seconds = max(1, int(float(payload.get("duration_seconds") or 30)))
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    agent_system_prompt("analysis")
                ),
            },
            {
                "role": "user",
                "content": (
                    "你正在拆解一条参考视频，不是在为我们的产品改写广告。"
                    "请严格还原输入素材中实际出现的主题、人物、场景、动作、台词、叙事结构和节奏；"
                    "不得主动加入恒温杯、奶瓶、98°F、夜间喂养或任何输入中不存在的产品与卖点。"
                    "请创建 analysis_report JSON 对象，字段包括：hook_3s、structure、voiceover_text、pacing、"
                    "keyframes、shot_breakdown、fingerprint、source_summary、source_evidence。"
                    f"原视频时长约 {duration_seconds} 秒。shot_breakdown 必须包含 5 个对象，每个含 number、timing、"
                    "visual、action、purpose、transition，并覆盖原视频完整时间线。"
                    "voiceover_text 必须忠实保留输入转写，不得替换为产品广告文案。"
                    "source_evidence 至少列出 3 段来自输入的原文短句，用于证明分析有据可查。"
                    "除 source_evidence 可保留原语言外，其他说明字段使用简体中文。输入转写如下：\n"
                    f"{transcript[:8000]}"
                ),
            },
        ],
    )
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "material_meta_ref": str(payload.get("source_material_id") or payload.get("source_url") or ""),
        "hook_3s": _string(response.get("hook_3s"), _source_hook(transcript)),
        "structure": _string_list(response.get("structure"), ["开场", "展开", "步骤", "结果", "收束"]),
        "voiceover_text": transcript,
        "pacing": _normalize_pacing(response.get("pacing")),
        "keyframes": _string_list(response.get("keyframes"), []),
        "shot_breakdown": _normalize_shot_breakdown(response.get("shot_breakdown"), transcript=transcript),
        "source_summary": _string(response.get("source_summary"), _source_hook(transcript)),
        "source_evidence": _string_list(response.get("source_evidence"), _source_evidence(transcript)),
        "fingerprint": _string(response.get("fingerprint"), f"ark-{meta.get('response_id') or 'analysis'}"),
    }
    _remove_product_template_contamination(report, transcript)
    artifacts.validate_artifact("analysis_report", report)
    return ToolResult.success(
        {"analysis_report": report},
        cost_cny=context.pricing_for("doubao_analyze"),
        meta={"tool": "doubao_analyze", "mock": False, **meta},
    )


def _normalize_pacing(value: Any) -> list[dict[str, Any]]:
    roles = ["钩子", "痛点", "方案", "证明", "行动号召"]
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value[:6]):
            if not isinstance(item, dict):
                continue
            start = _number(item.get("start_s"), index * 6)
            end = _number(item.get("end_s"), start + 6)
            if end <= start:
                end = start + 6
            result.append(
                {
                    "start_s": start,
                    "end_s": end,
                    "role": _string(item.get("role"), roles[min(index, len(roles) - 1)]),
                    "note": _string(item.get("note"), ""),
                }
            )
        if result:
            return result
    return [
        {"start_s": 0, "end_s": 6, "role": "钩子"},
        {"start_s": 6, "end_s": 12, "role": "痛点"},
        {"start_s": 12, "end_s": 18, "role": "方案"},
        {"start_s": 18, "end_s": 24, "role": "证明"},
        {"start_s": 24, "end_s": 30, "role": "行动号召"},
    ]


def _normalize_shot_breakdown(value: Any, *, transcript: str = "") -> list[dict[str, Any]]:
    fallback = _source_fallback_shot_breakdown(transcript) if transcript else _fallback_shot_breakdown()
    if not isinstance(value, list):
        return fallback
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value[:5]):
        if not isinstance(item, dict):
            continue
        base = fallback[index]
        result.append({
            "number": index + 1,
            "timing": _string(item.get("timing"), base["timing"]),
            "visual": _string(item.get("visual"), base["visual"]),
            "action": _string(item.get("action"), base["action"]),
            "purpose": _string(item.get("purpose"), base["purpose"]),
            "transition": _string(item.get("transition"), base["transition"]),
        })
    return result if len(result) == 5 else fallback


def _source_hook(transcript: str) -> str:
    text = " ".join(str(transcript or "").split()).strip()
    if not text:
        return "参考视频开场内容待补充。"
    for separator in ("。", "！", "？", ". ", "! ", "? "):
        first = text.split(separator, 1)[0].strip()
        if first:
            return first[:120]
    return text[:120]


def _source_evidence(transcript: str) -> list[str]:
    text = " ".join(str(transcript or "").split()).strip()
    if not text:
        return []
    chunks = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s*", text) if item.strip()]
    if not chunks:
        chunks = [text]
    return [item[:160] for item in chunks[:3]]


def _source_fallback_shot_breakdown(transcript: str) -> list[dict[str, str]]:
    evidence = _source_evidence(transcript) or ["原素材内容待补充"]
    roles = ["建立主题", "展开信息", "演示核心步骤", "展示结果", "完成收束"]
    result: list[dict[str, str]] = []
    for index in range(5):
        source = evidence[min(index, len(evidence) - 1)]
        result.append(
            {
                "number": index + 1,
                "timing": f"{index * 6}-{(index + 1) * 6}s",
                "visual": f"依据原素材第 {index + 1} 段画面核对：{source}",
                "action": f"还原与该段转写对应的原始动作，不添加输入中未出现的产品或人物。",
                "purpose": roles[index],
                "transition": "按原视频时间顺序衔接下一段。",
            }
        )
    return result


def _remove_product_template_contamination(report: dict[str, Any], transcript: str) -> None:
    forbidden = ("便携恒温杯", "恒温杯", "奶瓶", "98°F", "98 华氏度", "夜间喂养")
    absent = [token for token in forbidden if token.casefold() not in transcript.casefold()]
    if not absent:
        return

    def contaminated(value: Any) -> bool:
        text = str(value or "")
        return any(token in text for token in absent)

    if contaminated(report.get("hook_3s")):
        report["hook_3s"] = _source_hook(transcript)
    if contaminated(report.get("source_summary")):
        report["source_summary"] = _source_hook(transcript)
    if any(contaminated(item) for item in report.get("shot_breakdown") or []):
        report["shot_breakdown"] = _source_fallback_shot_breakdown(transcript)


def _fallback_shot_breakdown() -> list[dict[str, str]]:
    return [
        {"number": 1, "timing": "0-6s", "visual": "夜间喂养准备环境与产品位置", "action": "照护者把恒温杯放在床头柜", "purpose": "建立场景和问题", "transition": "从环境切入产品"},
        {"number": 2, "timing": "6-12s", "visual": "同一照护者面对等待中的奶液和奶瓶", "action": "查看等待状态并准备奶瓶", "purpose": "呈现等待痛点", "transition": "承接上一镜头的准备动作"},
        {"number": 3, "timing": "12-18s", "visual": "恒温杯与独立奶瓶并排特写", "action": "将奶液倒入恒温杯，不放入整只奶瓶", "purpose": "引入正确方案", "transition": "从痛点切到产品"},
        {"number": 4, "timing": "18-24s", "visual": "恒温杯杯嘴朝向独立干净奶瓶", "action": "从圆形出液口倒入奶瓶，温度只能显示98°F", "purpose": "完成使用证明", "transition": "延续同一双手和同一台面"},
        {"number": 5, "timing": "24-30s", "visual": "回到同一卧室和床头柜的稳定产品画面", "action": "照护者收好用品并停留在产品上", "purpose": "形成结果和行动号召", "transition": "回到开场构图收束"},
    ]


def _string(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return fallback


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)
