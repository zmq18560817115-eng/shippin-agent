from __future__ import annotations

import re
from typing import Any


EXPECTED_ROLES = ["钩子", "痛点", "方案", "证明", "行动号召"]
EXPECTED_TIMINGS = ["0-6s", "6-12s", "12-18s", "18-24s", "24-30s"]
VAGUE_CREATIVE_PHRASES = ("高级感", "氛围感", "品质生活", "轻松解决", "一键搞定", "必备神器", "开启美好")


def assess_strategy(strategy: dict[str, Any]) -> dict[str, Any]:
    checks = [
        _check("direction", len(str(strategy.get("content_direction") or "").strip()) >= 12, "内容方向必须具体且可执行"),
        _check("audience", bool(strategy.get("target_audience")), "必须明确目标受众"),
        _check("selling_points", len(strategy.get("selling_point_priority") or []) >= 2, "至少需要两个已获批卖点"),
        _check("hooks", bool(strategy.get("hook_options")), "至少需要一个可拍摄的钩子"),
        _check("cta", bool(strategy.get("cta_options")), "至少需要一个明确行动号召"),
        _check("guardrails", isinstance(strategy.get("product_guardrails"), dict) and bool(strategy.get("product_guardrails")), "产品安全规则必须为非空结构化对象"),
        _check("chinese_delivery", _chinese_ratio(str(strategy)) >= 0.18, "策略交付必须以简体中文为主"),
        _check("anti_template_copy", not _contains_any(str(strategy), VAGUE_CREATIVE_PHRASES), "策略不得使用模板化空话代替具体创意"),
    ]
    return _report("strategy", checks)


def assess_script(script: dict[str, Any]) -> dict[str, Any]:
    sections = script.get("sections") if isinstance(script.get("sections"), list) else []
    checks = [
        _check("structure", [item.get("role") for item in sections] == EXPECTED_ROLES, "五段角色必须为钩子、痛点、方案、证明、行动号召"),
        _check("timing", [item.get("timing") for item in sections] == EXPECTED_TIMINGS, "时间线必须连续覆盖 0-30 秒"),
        _check("scene_action_story", _all_fields(sections, "voiceover_zh", "scene_zh", "action_zh", "story_beat_zh"), "每段都必须包含旁白、场景、动作和剧情推进"),
        _check("narrative_diversity", _unique_ratio(sections, "story_beat_zh") >= 0.8, "五段剧情推进不能重复"),
        _check("action_diversity", _unique_ratio(sections, "action_zh") >= 0.8, "每段必须有不同且可见的动作"),
        _check("chinese_delivery", _chinese_ratio(" ".join(str(item.get("voiceover_zh") or "") for item in sections)) >= 0.35, "运营文案必须以简体中文交付"),
        _check("scene_specificity", _all_min_length(sections, "scene_zh", 18), "每段场景必须包含足够具体的环境、光线、道具或人物状态"),
        _check("spoken_naturalness", _all_bounded_length(sections, "voiceover_zh", 8, 70), "旁白必须简洁、可朗读，避免空泛或过长句子"),
        _check("causal_progression", _all_min_length(sections, "story_beat_zh", 14), "每段必须说明剧情变化及其承接作用"),
        _check(
            "anti_template_copy",
            not _contains_any(" ".join(str(item.get(key) or "") for item in sections for key in ("voiceover_zh", "story_beat_zh")), VAGUE_CREATIVE_PHRASES),
            "删除高级感、必备神器等模板化空话，改写为可见动作、具体变化或用户结果",
        ),
    ]
    if "恒温杯" in str(script.get("product_id") or "") and len(sections) >= 4:
        solution = str(sections[2].get("action_zh") or "")
        proof = str(sections[3].get("action_zh") or "")
        checks.extend(
            [
                _check("fill_direction", "倒入恒温杯" in solution, "方案镜头必须明确液体倒入恒温杯"),
                _check("pour_direction", "圆形出液口" in proof and "奶瓶" in proof, "证明镜头必须明确从圆形出液口倒入独立奶瓶"),
                _check("temperature", not _contains_forbidden_celsius(str(script)), "温标只能使用 98°F 华氏度"),
            ]
        )
    return _report("script", checks)


def assess_standalone_script(script: dict[str, Any]) -> dict[str, Any]:
    sections = script.get("sections") if isinstance(script.get("sections"), list) else []
    duration = float(script.get("total_duration_s") or 0)
    checks = [
        _check("structure", 3 <= len(sections) <= 8, "独立脚本应包含 3-8 个有效段落"),
        _check("timing", _continuous_timing(sections, duration), "段落时间必须连续并覆盖目标时长"),
        _check("scene_action_story", _all_fields(sections, "voiceover_zh", "scene_zh", "action_zh", "story_beat_zh"), "每段都必须包含旁白、场景、动作和剧情推进"),
        _check("narrative_diversity", _unique_ratio(sections, "story_beat_zh") >= 0.75, "各段剧情推进不能重复"),
        _check("action_diversity", _unique_ratio(sections, "action_zh") >= 0.75, "各段应使用不同且可见的动作"),
        _check("chinese_delivery", _chinese_ratio(" ".join(str(item.get("voiceover_zh") or "") for item in sections)) >= 0.35, "运营文案必须以简体中文交付"),
        _check("scene_specificity", _all_min_length(sections, "scene_zh", 18), "场景必须包含具体环境、光线、道具或人物状态"),
        _check("spoken_naturalness", _all_bounded_length(sections, "voiceover_zh", 4, 90), "旁白必须自然、可朗读，避免空泛或过长"),
        _check("anti_template_copy", not _contains_any(str(script), VAGUE_CREATIVE_PHRASES), "删除模板化空话，改写为具体动作和用户变化"),
        _check("temperature", not _contains_forbidden_celsius(str(sections)), "禁止使用摄氏温标冒充华氏温标"),
    ]
    return _report("standalone_script", checks)


def assess_storyboard(plan: dict[str, Any], script: dict[str, Any] | None = None) -> dict[str, Any]:
    shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
    durations = [float((shot.get("camera_motion") or {}).get("duration_sec") or 0) for shot in shots]
    motions = {str((shot.get("camera_motion") or {}).get("type") or "") for shot in shots}
    prompts = [str(shot.get("seedance_prompt") or "") for shot in shots]
    visual_copy = " ".join(str(shot.get("visual_zh") or shot.get("visual") or "") for shot in shots).casefold()
    checks = [
        _check("shot_count", len(shots) == 5, "分镜必须包含五个镜头"),
        _check("duration", len(durations) == 5 and abs(sum(durations) - 30) < 0.01, "五镜总时长必须为 30 秒"),
        _check("visual_diversity", _unique_ratio(shots, "visual") >= 0.8, "镜头画面不能重复"),
        _check("camera_variety", len(motions - {""}) >= 3, "至少使用三种景别或镜头运动"),
        _check("continuity_lock", bool(prompts) and all("continuity lock" in prompt.casefold() for prompt in prompts), "每镜提示词必须包含连续性锁定"),
        _check("product_lock", bool(prompts) and all("white-background hero" in prompt.casefold() for prompt in prompts), "每镜提示词必须锚定获批产品白底主图"),
        _check("chinese_fields", _all_fields(shots, "visual_zh", "seedance_prompt_zh"), "每镜必须提供中文画面与生成提示"),
        _check("no_generated_text", not any(token in visual_copy for token in ("配文", "字幕", "文字叠加", "屏幕文字", "标题文字", "slogan", "caption", "overlay text")), "生成画面不得要求字幕、配文或其他可读文字"),
        _check("visual_specificity", _all_min_length(shots, "visual_zh", 20), "每镜必须写清主体位置、环境和可见动作，不能只给抽象风格词"),
        _check("prompt_specificity", _all_min_length(shots, "seedance_prompt_zh", 24), "每镜生成提示必须具体、可执行并包含连续性线索"),
        _check(
            "production_prompt_contract",
            bool(prompts) and all(all(token in prompt.casefold() for token in ("continuity lock", "product identity lock", "action continuity", "camera contract", "negative constraints")) for prompt in prompts),
            "每镜提示词必须统一包含场景连续性、产品身份、动作承接、镜头语言与负面约束",
        ),
        _check(
            "anti_vague_visuals",
            not _contains_any(" ".join(str(shot.get(key) or "") for shot in shots for key in ("visual_zh", "seedance_prompt_zh")), VAGUE_CREATIVE_PHRASES),
            "分镜不得用高级感、氛围感等空词代替主体位置、环境、动作和镜头设计",
        ),
    ]
    if script:
        sections = script.get("sections") if isinstance(script.get("sections"), list) else []
        checks.append(
            _check(
                "script_information_conservation",
                len(sections) == len(shots)
                and all(
                    str(shot.get("script_role") or "") == str(section.get("role") or "")
                    and str(shot.get("script_timing") or "") == str(section.get("timing") or "")
                    and str(shot.get("script_scene_zh") or "") == str(section.get("scene_zh") or "")
                    and str(shot.get("script_action_zh") or "") == str(section.get("action_zh") or "")
                    and str(shot.get("script_story_beat_zh") or "") == str(section.get("story_beat_zh") or "")
                    for shot, section in zip(shots, sections)
                ),
                "分镜必须逐段保留脚本角色、时间、场景、动作和剧情推进，不得在模型生成时丢失",
            )
        )
    product_id = str((script or {}).get("product_id") or "")
    if "恒温杯" in product_id and len(shots) >= 4:
        proof = " ".join(str(shots[3].get(key) or "") for key in ("visual", "visual_zh", "seedance_prompt"))
        checks.extend(
            [
                _check("pour_direction", "round spout" in proof.casefold() or "圆形出液口" in proof, "第四镜必须展示从圆形出液口倒入独立奶瓶"),
                _check("temperature", not _contains_forbidden_celsius(str(plan)), "禁止出现 98°C，只允许 98°F"),
            ]
        )
    return _report("storyboard", checks)


def _check(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "message": message}


def _report(kind: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(bool(item["passed"]) for item in checks)
    score = round(100 * passed / len(checks)) if checks else 0
    issues = [item["message"] for item in checks if not item["passed"]]
    return {
        "version": "1.0",
        "kind": kind,
        "status": "PASS" if score >= 80 and not issues else "NEEDS_REWRITE",
        "score": score,
        "checks": checks,
        "issues": issues,
        "rewrite_instruction": "；".join(issues),
    }


def _all_fields(items: list[dict[str, Any]], *names: str) -> bool:
    return bool(items) and all(all(str(item.get(name) or "").strip() for name in names) for item in items)


def _all_min_length(items: list[dict[str, Any]], name: str, minimum: int) -> bool:
    return bool(items) and all(len(str(item.get(name) or "").strip()) >= minimum for item in items)


def _all_bounded_length(items: list[dict[str, Any]], name: str, minimum: int, maximum: int) -> bool:
    if not items:
        return False
    lengths = [len(str(item.get(name) or "").strip()) for item in items]
    return all(minimum <= length <= maximum for length in lengths)


def _continuous_timing(items: list[dict[str, Any]], duration: float) -> bool:
    expected = 0
    for item in items:
        match = re.fullmatch(r"(\d+)-(\d+)s", str(item.get("timing") or ""))
        if not match or int(match.group(1)) != expected or int(match.group(2)) <= expected:
            return False
        expected = int(match.group(2))
    return bool(items) and abs(expected - duration) <= 1


def _unique_ratio(items: list[dict[str, Any]], name: str) -> float:
    values = [" ".join(str(item.get(name) or "").casefold().split()) for item in items]
    values = [value for value in values if value]
    return len(set(values)) / len(items) if items else 0.0


def _chinese_ratio(value: str) -> float:
    letters = re.findall(r"[A-Za-z\u3400-\u9fff]", value)
    chinese = re.findall(r"[\u3400-\u9fff]", value)
    return len(chinese) / len(letters) if letters else 0.0


def _contains_any(value: str, phrases: tuple[str, ...]) -> bool:
    normalized = value.casefold()
    return any(phrase.casefold() in normalized for phrase in phrases)


def _contains_forbidden_celsius(value: str) -> bool:
    normalized = value.casefold()
    for match in re.finditer(r"98\s*(?:°\s*c|℃)", normalized):
        context = normalized[max(0, match.start() - 48):match.start()]
        if any(token in context for token in ("禁止", "不得", "不能", "避免", "never", "do not", "don't", "no ", "without")):
            continue
        return True
    return False
