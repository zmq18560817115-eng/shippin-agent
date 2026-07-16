from __future__ import annotations

from typing import Any

from libshared import artifacts
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
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "material_meta_ref": str(payload.get("source_material_id") or payload.get("source_url") or ""),
        "hook_3s": "夜间喂养准备，也可以更轻松。",
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
        "fingerprint": "mock-analysis",
    }
    artifacts.validate_artifact("analysis_report", report)
    return ToolResult.success(
        {"analysis_report": report},
        cost_cny=context.pricing_for("doubao_analyze") if not context.mock else 0.0,
        meta={"tool": "doubao_analyze", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    transcript = str(payload.get("transcript_text") or payload.get("source_url") or "Manual competitor link intake.")
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze short-video structure for brand-safe overseas localization. "
                    "Return strict JSON only. Do not copy competitor wording or unsupported claims."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create an analysis_report JSON object with fields: hook_3s, structure, voiceover_text, pacing, keyframes, shot_breakdown, fingerprint for a 30-second video. "
                    "shot_breakdown must contain 5 objects with number, timing, visual, action, purpose, transition. Product: portable warming cup. "
                    "Use only generic structure insights from the source. Source text/link: "
                    f"{transcript[:1500]}"
                ),
            },
        ],
    )
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "material_meta_ref": str(payload.get("source_material_id") or payload.get("source_url") or ""),
        "hook_3s": _string(response.get("hook_3s"), "Bottle prep without the long wait."),
        "structure": _string_list(response.get("structure"), ["钩子", "痛点", "方案", "行动号召"]),
        "voiceover_text": _string(response.get("voiceover_text"), transcript),
        "pacing": _normalize_pacing(response.get("pacing")),
        "keyframes": _string_list(response.get("keyframes"), []),
        "shot_breakdown": _normalize_shot_breakdown(response.get("shot_breakdown")),
        "fingerprint": _string(response.get("fingerprint"), f"ark-{meta.get('response_id') or 'analysis'}"),
    }
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


def _normalize_shot_breakdown(value: Any) -> list[dict[str, Any]]:
    fallback = _fallback_shot_breakdown()
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
