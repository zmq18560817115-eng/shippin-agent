from __future__ import annotations

import json
from typing import Any

from libshared import artifacts
from libshared.agent_contracts import agent_system_prompt
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


@register_tool("doubao_review")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
        return _execute_real(payload, context)
    project_id = str(payload.get("project_id") or "ref-mock")
    script_copy = payload.get("script_copy") or {}
    script_text = json.dumps(script_copy.get("sections") or [], ensure_ascii=False)
    source_text = str(payload.get("review_source_text") or "")
    product_id = str(payload.get("product_id") or script_copy.get("product_id") or "便携恒温杯")
    guardrails = str(payload.get("product_guardrails") or "")
    warming_product = _is_warming_product(product_id, guardrails)
    violations = _mock_violations(source_text, prefix="源稿", warming_product=warming_product)
    if script_text and script_text != "[]":
        violations += _mock_violations(script_text, prefix="结构化脚本", warming_product=warming_product)
    status = "BLOCKED" if violations else "PASS"
    report = {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product_id,
        "artifact_type": "review_report",
        "status": status,
        "scores": {
            "hook": 8,
            "clarity": 8,
            "compliance": 2 if violations else 10,
            "product_fit": 9,
            "pacing": 8,
            "cta": 8,
            "asset_traceability": 9,
        },
        "comments": violations or ["演练审核通过：未发现与当前产品事实、使用边界或广告表达规则冲突的内容。"],
        "input_summary": (source_text or script_text)[:500],
    }
    artifacts.validate_artifact("review_report", report)
    return ToolResult.success(
        {"review_report": report},
        cost_cny=context.pricing_for("doubao_review") if not context.mock else 0.0,
        meta={"tool": "doubao_review", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _mock_violations(script_text: str, *, prefix: str, warming_product: bool = True) -> list[str]:
    checks = [
        (("保证治愈", "医疗效果", "促进泌乳", "增加奶量"), "检测到未经批准的医疗或保证性宣称。"),
        (("全网第一", "最好", "百分百", "100%有效"), "检测到绝对化或保证性广告表达。"),
    ]
    if warming_product:
        checks[:0] = [
            (("98°C", "98 摄氏", "98摄氏"), "检测到错误温标：产品可见温度只能是 98°F，禁止 98°C。"),
            (("奶瓶放入杯", "奶瓶插入杯", "把奶瓶放进"), "检测到错误使用方式：恒温杯与奶瓶必须是两个独立物体。"),
        ]
    clauses = [clause.strip() for clause in script_text.replace("；", "。").replace(";", ".").split("。")]
    violations = []
    for tokens, message in checks:
        if any(
            token in clause and not any(negation in clause for negation in ("禁止", "不得", "不能", "不可", "避免"))
            for clause in clauses
            for token in tokens
        ):
            violations.append(message)
    return [f"{prefix}：{message}" for message in violations]


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    script_copy = payload.get("script_copy") or {}
    analysis_report = payload.get("analysis_report") or {}
    review_source_text = str(payload.get("review_source_text") or "")
    product_id = str(payload.get("product_id") or script_copy.get("product_id") or "当前产品")
    product_guardrails = str(payload.get("product_guardrails") or "")
    warming_product = _is_warming_product(product_id, product_guardrails)
    product_checks = (
        "同时检查温度只能显示 98°F，恒温杯与奶瓶为两个独立物体。"
        if warming_product
        else "只依据提供的产品事实审核，不得把恒温杯、奶瓶、奶液或温标规则套用到其他产品。"
    )
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    agent_system_prompt("review")
                    + "你负责审核短视频脚本、分镜说明或广告文案的合规性、产品事实与使用动作。"
                    "只返回严格 JSON，状态只能是 PASS、WARNING 或 BLOCKED，评论必须使用简体中文。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "审核以下脚本。遇到未经批准的医疗效果、保证性、第一/最好、无痛、泌乳、竞品贬低或不安全使用宣称时必须阻断。"
                    f"{product_checks}返回 status、scores、comments。"
                    f"审核产品或主题：{product_id}。获批产品事实：{product_guardrails or '未提供'}。"
                    f"用户提交的原稿：{review_source_text}。素材分析：{analysis_report}。结构化脚本：{script_copy}"
                ),
            },
        ],
        temperature=0.1,
    )
    status = str(response.get("status") or "PASS").upper()
    if status not in {"PASS", "WARNING", "BLOCKED"}:
        status = "WARNING"
    report = {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product_id,
        "artifact_type": "review_report",
        "status": status,
        "scores": response.get("scores") if isinstance(response.get("scores"), dict) else {},
        "comments": _comments(response.get("comments")),
        "input_summary": (review_source_text or json.dumps(script_copy, ensure_ascii=False))[:500],
    }
    artifacts.validate_artifact("review_report", report)
    return ToolResult.success(
        {"review_report": report},
        cost_cny=context.pricing_for("doubao_review"),
        meta={"tool": "doubao_review", "mock": False, **meta},
    )


def _comments(value: Any) -> list[str]:
    if isinstance(value, list):
        comments = [str(item).strip() for item in value if str(item).strip()]
        if comments:
            return comments
    if value:
        return [str(value).strip()]
    return ["豆包审核已完成。"]


def _is_warming_product(product_id: str, product_guardrails: str = "") -> bool:
    normalized = f"{product_id} {product_guardrails}".casefold()
    return any(token in normalized for token in ("恒温杯", "温奶", "warming cup", "bottle warmer", "98°f", "98 f"))
