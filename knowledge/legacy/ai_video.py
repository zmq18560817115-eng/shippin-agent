"""AI 分镜视频：空镜 (AI_BROLL) 与脚本展示镜 (AI_VIDEO) 的生成策略与 Prompt。"""
from __future__ import annotations

import os
import re
from typing import Any

from .character_assets import build_character_prompt_block, shot_needs_person
from .product_usage import THERMOS_USAGE_EN, THERMOS_PRODUCT_EN

AI_VIDEO_FOOTAGE = frozenset({"AI_BROLL", "AI_VIDEO"})
SEEDANCE_PROMPT_LIMIT = 1990


def ai_video_mode() -> str:
    """broll = 仅痛点空镜；script = 按脚本为各镜生成短视频展示。"""
    return (os.getenv("AI_VIDEO_MODE") or "broll").strip().lower()


def ai_video_on_finish() -> bool:
    if (os.getenv("SKIP_SEEDANCE") or "").strip().lower() in ("1", "true", "yes"):
        return False
    raw = (os.getenv("AI_VIDEO_ON_FINISH") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def ai_video_concat_enabled() -> bool:
    return (os.getenv("AI_VIDEO_CONCAT") or "1").strip().lower() not in ("0", "false", "no", "off")


def ai_video_concat_min_shots() -> int:
    raw = (os.getenv("AI_VIDEO_CONCAT_MIN_SHOTS") or "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def ai_video_max_shots() -> int:
    """0 = 不限制；正整数 = 每次最多生成几镜（按镜号顺序）。"""
    raw = (os.getenv("AI_VIDEO_MAX_SHOTS") or "0").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def shot_generates_video(footage_type: str | None, mode: str | None = None) -> bool:
    mode = mode or ai_video_mode()
    ft = (footage_type or "").strip()
    if mode == "script":
        return ft in AI_VIDEO_FOOTAGE or ft == "LIVE_ACTION"
    return ft == "AI_BROLL"


def footage_label(footage_type: str | None) -> str:
    ft = (footage_type or "").strip()
    if ft == "AI_BROLL":
        return "AI 空镜"
    if ft == "AI_VIDEO":
        return "AI 分镜"
    return "实拍"


def _clean_en(text: str, limit: int = 120) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    return t[:limit]


def _clamp_prompt(text: str, limit: int = SEEDANCE_PROMPT_LIMIT) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= limit:
        return t
    return t[: limit - 3].rstrip() + "..."


def sanitize_seedance_prompt(text: str) -> str:
    """Normalize and hard-cap prompts before they hit SeedanceRequest validation."""
    return _clamp_prompt(text, SEEDANCE_PROMPT_LIMIT)


def _usage_compact() -> str:
    return THERMOS_USAGE_EN


def _safe_suffix(character: dict[str, Any] | None, role: str, *, aspect_ratio: str = "9:16") -> str:
    from .video_production import aspect_ratio_prompt

    ratio_hint = aspect_ratio_prompt(aspect_ratio)
    if character and shot_needs_person(role):
        return f"{ratio_hint}, TikTok product ad style, no medical claim, match approved person reference"
    return f"no person face, no medical claim, {ratio_hint}, TikTok product ad style"


def _product_hero_lock() -> str:
    return (
        "match approved white-background product hero photo (白底主图) exactly for color, silhouette, lid, display, logo zone; "
        "do NOT copy product shape from lifestyle/scenario listing images; no redesign or recolor"
    )


def build_shot_video_prompt(
    *,
    role: str,
    pack_shot: dict[str, Any],
    story_shot: dict[str, Any] | None = None,
    scene_en: str = "daily baby feeding",
    product_name: str = "portable milk-warming thermos cup",
    character: dict[str, Any] | None = None,
    aspect_ratio: str = "9:16",
) -> str:
    """从脚本镜位合成 SeedDance 英文 Prompt。"""
    story_shot = story_shot or {}
    explicit = str(pack_shot.get("seedance_prompt") or story_shot.get("notes") or "").strip()
    if len(explicit) >= 10:
        from .camera_motion import apply_motion_to_seedance_prompt
        from .product_staging import is_fixed_product, pour_usage_prompt_suffix

        explicit = apply_motion_to_seedance_prompt(explicit, pack_shot)
        hero_lock = _product_hero_lock()
        if "white-background" not in explicit.lower() and "hero product photo" not in explicit.lower():
            explicit = f"{explicit} {hero_lock}"
        pour_hint = pour_usage_prompt_suffix(product_name, role)
        if pour_hint and pour_hint.lower() not in explicit.lower():
            explicit = f"{explicit} {pour_hint}"
        if character and shot_needs_person(role) and "approved caregiver" not in explicit:
            person = build_character_prompt_block(character)
            return _clamp_prompt(f"{explicit} {person}")
        return _clamp_prompt(explicit)

    vo = _clean_en(
        str(pack_shot.get("voiceover_en") or pack_shot.get("subtitle_en") or story_shot.get("copy") or "")
    )
    visual = str(pack_shot.get("visual_prompt") or pack_shot.get("visual") or story_shot.get("visual") or "")
    safe = _safe_suffix(character, role, aspect_ratio=aspect_ratio)
    person = build_character_prompt_block(character) if character and shot_needs_person(role) else ""
    cup = THERMOS_PRODUCT_EN
    usage = _usage_compact()
    hero_lock = _product_hero_lock()

    role_key = (role or "").strip()
    if role_key == "钩子":
        if character and shot_needs_person(role_key):
            return _clamp_prompt(
                f"Hook opening, {scene_en}, {person}, medium shot with {cup} beside separate baby bottle, "
                f"cinematic soft light, subtle push-in, {safe}. {usage}. {hero_lock}. "
                f"Voiceover mood: {vo or 'attention grabbing'}"
            )
        return _clamp_prompt(
            f"Hook shot opening, {scene_en}, sharp close-up of {cup} on table, baby bottle beside, "
            f"cinematic soft light, subtle push-in, {safe}. {usage}. {hero_lock}. "
            f"Voiceover mood: {vo or 'attention grabbing'}"
        )
    if role_key == "痛点":
        if character and shot_needs_person(role_key):
            return _clamp_prompt(
                f"Problem moment, {scene_en}, {person}, cold milk in baby bottle, bulky warmer contrast, "
                f"moody lighting, realistic hand physics, {safe}. {usage}. {hero_lock}. {vo}"
            )
        return _clamp_prompt(
            f"Problem moment, {scene_en}, cold milk in baby bottle, bulky old bottle warmer contrast, "
            f"moody lighting, {safe}. {usage}. {hero_lock}. {vo}"
        )
    if role_key == "方案":
        if character and shot_needs_person(role_key):
            return _clamp_prompt(
                f"Product demo, {scene_en}, {person}, side angle — flip-top lid open, pour milk INTO {cup}, "
                f"then tilt to pour warm milk OUT from lid spout into baby feeding bottle, realistic pour physics, "
                f"vertical display visible, {safe}. {usage}. {hero_lock}. {vo}"
            )
        return _clamp_prompt(
            f"Product demo, {scene_en}, flip-top lid open — pour milk INTO {cup}; tilt to pour warm milk OUT "
            f"from lid spout into baby feeding bottle, {safe}. {usage}. {hero_lock}. {vo}"
        )
    if role_key == "证明":
        return _clamp_prompt(
            f"Proof detail shot, {scene_en}, macro of body-warm milk pouring OUT from lid spout of {cup} "
            f"into baby feeding bottle, no steam plume or boiling bubbles, hinged lid open, {safe}. {usage}. {hero_lock}. {vo}"
        )
    if role_key == "行动号召":
        if character and shot_needs_person(role_key):
            return _clamp_prompt(
                f"CTA closing, {scene_en}, {person}, smiling with {cup} and baby bottle on clean surface, "
                f"flip-top lid closed, digital display visible, {safe}. {usage}. {hero_lock}. {vo}"
            )
        return _clamp_prompt(
            f"CTA closing shot, {scene_en}, {cup} with flip-top lid closed, baby bottle beside, "
            f"digital display visible, {safe}. {usage}. {hero_lock}. {vo}"
        )

    return _clamp_prompt(
        f"{scene_en}, {cup}, {_clean_en(visual, 80)}, cinematic product b-roll, {safe}. {usage}. {hero_lock}. {vo}"
    )


def pipeline_label(mode: str | None = None) -> str:
    mode = mode or ai_video_mode()
    if mode == "script":
        return "脚本生成 → 分镜 → 各镜 Prompt → SeedDance 2.0 → 分镜短视频 → 成稿 zip"
    return "脚本生成 → 分镜生成 → 视频 Prompt → SeedDance 2.0 → 输出视频 → 保存成稿"
