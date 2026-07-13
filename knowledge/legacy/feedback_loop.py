"""成稿反馈 → 下次同产品/同场景生成的约束闭环。"""
from __future__ import annotations

import re
from typing import Any

from .feedback_tags import ADOPTED_FOR_LOOP, ISSUE_TAG_DEFS
from .library_api import list_feedback, load_feedback


def _parse_engagement(raw: str) -> float:
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return -1.0
    if text.endswith("%"):
        try:
            return float(text[:-1])
        except ValueError:
            return -1.0
    try:
        val = float(text)
        return val * 100 if 0 < val <= 1 else val
    except ValueError:
        return -1.0


def _scenario_overlap(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return True
    set_a = {str(x).strip() for x in a if str(x).strip()}
    set_b = {str(x).strip() for x in b if str(x).strip()}
    return bool(set_a & set_b)


def _constraint_lines_for_record(record: dict[str, Any]) -> tuple[list[str], list[str]]:
    zh: list[str] = []
    en: list[str] = []
    for tag_id in record.get("issue_tags") or []:
        defn = ISSUE_TAG_DEFS.get(tag_id)
        if defn:
            zh.append(defn["hint_zh"])
            en.append(defn["hint_en"])
    manual = str(record.get("manual_edits") or "").strip()
    if manual:
        zh.append(manual)
        en.append(manual)
    notes = str(record.get("notes") or "").strip()
    if notes and notes != "交付后由剪辑/运营填写人工修改与投放数据，用于反哺模型":
        zh.append(notes)
    return zh, en


def query_adopted_feedback(
    product_id: str,
    scenario_tags: list[str] | None = None,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    pid = str(product_id or "").strip()
    if not pid:
        return []
    tags = [str(t) for t in (scenario_tags or []) if str(t).strip()]
    matched: list[dict[str, Any]] = []
    for row in list_feedback():
        if row.get("adopted") not in ADOPTED_FOR_LOOP:
            continue
        if str(row.get("product_id") or "").strip() != pid:
            continue
        rec_tags = row.get("scenario_tags") or []
        if tags and rec_tags and not _scenario_overlap(tags, rec_tags):
            continue
        matched.append(row)
    matched.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return matched[:limit]


def best_publish_hints(product_id: str, *, limit: int = 3) -> list[dict[str, Any]]:
    pid = str(product_id or "").strip()
    if not pid:
        return []
    rows: list[dict[str, Any]] = []
    for row in list_feedback():
        if row.get("adopted") not in ADOPTED_FOR_LOOP:
            continue
        if str(row.get("product_id") or "").strip() != pid:
            continue
        score = _parse_engagement((row.get("publish") or {}).get("engagement", ""))
        if score < 0:
            continue
        rows.append({**row, "_engagement_score": score})
    rows.sort(key=lambda r: r.get("_engagement_score", -1), reverse=True)
    return rows[:limit]


def build_feedback_constraints(
    product_id: str,
    scenario_tags: list[str] | None = None,
) -> dict[str, Any]:
    adopted = query_adopted_feedback(product_id, scenario_tags)
    zh_lines: list[str] = []
    en_lines: list[str] = []
    issue_union: list[str] = []
    sources: list[dict[str, str]] = []

    for rec in adopted:
        z, e = _constraint_lines_for_record(rec)
        for line in z:
            if line not in zh_lines:
                zh_lines.append(line)
        for line in e:
            if line not in en_lines:
                en_lines.append(line)
        for tag_id in rec.get("issue_tags") or []:
            if tag_id not in issue_union:
                issue_union.append(tag_id)
        sources.append({
            "slug": str(rec.get("slug") or ""),
            "adopted": str(rec.get("adopted") or ""),
            "scenario_tags": "、".join(rec.get("scenario_tags") or []),
        })

    publish_hints = best_publish_hints(product_id)
    template_hint: dict[str, Any] | None = None
    if publish_hints:
        top = publish_hints[0]
        template_hint = {
            "slug": top.get("slug", ""),
            "engagement": (top.get("publish") or {}).get("engagement", ""),
            "scenario_tags": top.get("scenario_tags") or [],
            "template_id": top.get("template_id", ""),
            "template_label": top.get("template_label", ""),
        }

    return {
        "product_id": product_id,
        "scenario_tags": scenario_tags or [],
        "matched_count": len(adopted),
        "source_slugs": [s["slug"] for s in sources if s.get("slug")],
        "sources": sources,
        "issue_tags": issue_union,
        "constraints_zh": zh_lines,
        "constraints_en": en_lines,
        "template_hint": template_hint,
    }


def format_constraints_for_llm(block: dict[str, Any]) -> str:
    if not block.get("constraints_zh"):
        return ""
    lines = ["## 历史已采纳反馈约束（必须遵守，避免重复犯错）"]
    for i, line in enumerate(block["constraints_zh"], 1):
        lines.append(f"{i}. {line}")
    if block.get("source_slugs"):
        lines.append(f"- 来源成稿: {', '.join(block['source_slugs'][:5])}")
    hint = block.get("template_hint")
    if hint and hint.get("engagement"):
        sc_tags = "、".join(hint.get("scenario_tags") or [])
        tpl = hint.get("template_label") or hint.get("template_id") or ""
        extra = f"历史高互动成片（互动率 {hint['engagement']}）"
        if sc_tags:
            extra += f"偏好场景: {sc_tags}"
        if tpl:
            extra += f"；结构模板参考: {tpl}"
        lines.append(f"- {extra}（仍以本次场景标签与竞品节奏为主）")
    return "\n".join(lines)


def format_constraints_en_suffix(block: dict[str, Any], limit: int = 320) -> str:
    parts = list(block.get("constraints_en") or [])
    if not parts:
        return ""
    text = "FEEDBACK CONSTRAINTS: " + "; ".join(parts)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def apply_feedback_to_pack(pack: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
    if not block.get("constraints_zh"):
        pack["feedback_constraints"] = block
        return pack
    suffix_zh = "；".join(block["constraints_zh"][:6])
    suffix_en = format_constraints_en_suffix(block)
    for shot in pack.get("storyboard") or []:
        vp = str(shot.get("visual_prompt") or "")
        if suffix_zh and suffix_zh not in vp:
            shot["visual_prompt"] = f"{vp}；反馈约束：{suffix_zh}" if vp else f"反馈约束：{suffix_zh}"
        sd = str(shot.get("seedance_prompt") or "")
        if suffix_en and sd and suffix_en not in sd:
            shot["seedance_prompt"] = f"{sd} {suffix_en}"
    if pack.get("seedance_prompts"):
        pack["seedance_prompts"] = [
            s.get("seedance_prompt", "")
            for s in pack.get("storyboard") or []
            if s.get("footage_type") in ("AI_BROLL", "AI_VIDEO") and s.get("seedance_prompt")
        ]
    pack["feedback_constraints"] = block
    return pack


def preview_constraints(product_id: str, scenario_tags: list[str] | None = None) -> dict[str, Any]:
    """API 预览：下次生成将带入的约束。"""
    block = build_feedback_constraints(product_id, scenario_tags)
    block["prompt_block"] = format_constraints_for_llm(block)
    return block
