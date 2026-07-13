"""按用户所选场景标签生成一致的口播与分镜画面 prompt。"""

from __future__ import annotations

from typing import Any

from .ai_video import default_footage_for_role, build_role_video_prompt
from .camera_motion import default_camera_motion, ensure_shot_camera_motion
from .character_assets import resolve_character
from .product_usage import (
    THERMOS_USAGE_ZH,
    THERMOS_USAGE_EN,
    THERMOS_PRODUCT_EN,
    THERMOS_VISUAL_RULES_ZH,
)

# 互斥场景组：同组可多标签，跨组多选时以第一个场景标签为准
SCENE_DEFS: list[dict[str, Any]] = [
    {
        "id": "bedroom",
        "match": ("卧室", "夜间", "夜奶"),
        "zh": "夜间卧室喂奶",
        "en": "nighttime nursery bedroom feeding",
        "title": "for calmer night feeds",
        "subtitle": "Warm milk by the bedside, in minutes",
        "cta": "Save this for your next night feed.",
        "seedance": (
            "Dim nursery bedroom at night, cold milk in baby bottle beside bedside table, "
            f"separate {THERMOS_PRODUCT_EN} on nightstand, soft shadows, slow push-in, "
            f"no person face, no medical claim, {THERMOS_USAGE_EN}, 9:16"
        ),
    },
    {
        "id": "car",
        "match": ("车内", "杯架"),
        "zh": "车内杯架加热",
        "en": "in-car cup holder warming",
        "title": "for parents on the road",
        "subtitle": "Warm milk in the cup holder, in minutes",
        "cta": "Save this before your next car ride with baby.",
        "seedance": (
            f"Car interior cup holder, {THERMOS_PRODUCT_EN} with warm milk inside, baby bottle "
            f"separate on seat, daylight through windshield, steady shot, no person face, "
            f"no medical claim, {THERMOS_USAGE_EN}, 9:16"
        ),
    },
    {
        "id": "travel",
        "match": ("机场", "旅途", "长途"),
        "zh": "旅途出行",
        "en": "airport or travel trip",
        "title": "for traveling parents",
        "subtitle": "Warm milk anywhere you travel, in minutes",
        "cta": "Save this for your next trip with baby.",
        "seedance": (
            f"Airport lounge or travel bag flat lay, {THERMOS_PRODUCT_EN}, baby bottle beside it, "
            f"soft ambient light, slow push-in, no medical claim, {THERMOS_USAGE_EN}, 9:16"
        ),
    },
    {
        "id": "outdoor",
        "match": ("公园", "遛娃"),
        "zh": "公园遛娃",
        "en": "park outing with baby",
        "title": "for outdoor family days",
        "subtitle": "Warm milk at the park, in minutes",
        "cta": "Save this for your next park day.",
        "seedance": (
            f"Park bench with diaper bag, {THERMOS_PRODUCT_EN} and separate baby bottle, "
            f"natural daylight, gentle breeze, no person face, no medical claim, {THERMOS_USAGE_EN}, 9:16"
        ),
    },
    {
        "id": "office",
        "match": ("办公室", "背奶"),
        "zh": "办公室背奶",
        "en": "office pumping or bottle prep",
        "title": "for working moms",
        "subtitle": "Quick warm milk at the office, in minutes",
        "cta": "Save this for your workday routine.",
        "seedance": (
            f"Quiet office desk corner, {THERMOS_PRODUCT_EN} warming milk, baby bottle ready beside, "
            f"soft indoor light, no person face, no medical claim, {THERMOS_USAGE_EN}, 9:16"
        ),
    },
    {
        "id": "public",
        "match": ("餐厅", "商场", "临时冲奶"),
        "zh": "餐厅商场临时冲奶",
        "en": "restaurant or mall bottle prep",
        "title": "for dining out with baby",
        "subtitle": "Warm milk on the go, even at the mall",
        "cta": "Save this before your next meal out.",
        "seedance": (
            f"Cafe table corner, hands tilting {THERMOS_PRODUCT_EN}, warm milk streaming from circular pour spout hole "
            f"in flip-top lid into baby feeding bottle, {THERMOS_USAGE_EN}, 9:16"
        ),
    },
]


def _classify_tag(tag: str) -> str | None:
    for scene in SCENE_DEFS:
        if any(k in tag for k in scene["match"]):
            return scene["id"]
    return None


def scenario_conflict_note(scenario_tags: list[str]) -> str:
    groups: list[str] = []
    for tag in scenario_tags:
        gid = _classify_tag(tag)
        if gid and gid not in groups:
            groups.append(gid)
    if len(groups) <= 1:
        return ""
    names = []
    for gid in groups:
        for s in SCENE_DEFS:
            if s["id"] == gid:
                names.append(s["zh"])
                break
    return f"已选多个互斥场景（{'、'.join(names)}），成片将统一按首要场景「{scenario_tags[0]}」生成，避免卧室/车载等画面冲突。"


def resolve_scenario_profile(scenario_tags: list[str]) -> dict[str, Any]:
    primary = scenario_tags[0] if scenario_tags else ""
    for tag in scenario_tags:
        for scene in SCENE_DEFS:
            if any(k in tag for k in scene["match"]):
                return {**scene, "primary_tag": tag, "all_tags": scenario_tags}
    return {
        **SCENE_DEFS[0],
        "primary_tag": primary or SCENE_DEFS[0]["zh"],
        "all_tags": scenario_tags,
    }


def _blob(tags: list[str]) -> str:
    return "、".join(tags)


def thermos_voiceovers(market: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    pains = _blob(market.get("pain_tags") or [])
    selling = _blob(market.get("selling_tags") or [])
    sid = profile["id"]

    if sid == "bedroom":
        hook = "Middle-of-the-night feeds and milk still not warm enough?"
        if "慢" in pains or "哭闹" in pains or "等待" in pains:
            hook = "Still waiting forever to warm milk during night feeds?"
        pain = "Fumbling in the dark makes every feed harder."
        if "传统" in pains or "太大" in pains or "不便携" in pains or "笨重" in pains:
            pain = "A bulky warmer has no place on your nightstand."
        elif "热水" in pains or "没热水" in pains:
            pain = "No convenient hot water when baby wakes up hungry."
        elif "温度" in pains:
            pain = "Uneven temperature is the last thing you need at 2 a.m."
        sell = "Pour milk into this warming thermos cup, heat evenly, then into baby's bottle."
        if "均匀" in selling or "温控" in selling:
            sell = "Pour in, even heat inside the thermos cup, then pour out to the bottle."
        elif "充电" in selling or "USB" in selling.upper():
            sell = "USB-C rechargeable thermos cup — warm milk by the bed, pour when ready."
        elif "便携" in selling:
            sell = "Compact thermos cup stays on your nightstand for quick pour-and-feed."
        proof = "Warm milk poured out ready for the bottle — without leaving the room."
        cta = profile.get("cta", "Save this for your next night feed.")
        return [hook, pain, sell, proof, cta]

    if sid == "car":
        hook = "No easy way to warm a bottle in the car?"
        pain = "Waiting on the road makes a hungry baby harder to soothe."
        if "热水" in pains or "没热水" in pains:
            pain = "No hot water in the car when baby needs a bottle."
        elif "太大" in pains or "不便携" in pains:
            pain = "A bulky warmer does not fit your cup holder routine."
        sell = "Fits the cup holder and heats evenly in minutes."
        if "杯架" in selling or "便携" in selling:
            sell = "Designed for your cup holder — warm milk on the drive."
        proof = "Compact in the cup holder, easy to grab on every drive."
        return [hook, pain, sell, proof, profile.get("cta", "")]

    if sid == "travel":
        hook = "No hot water when you're out with baby?"
        primary = str(profile.get("primary_tag") or "")
        if "机场" in primary:
            hook = "At the airport with baby — still no easy way to warm a bottle?"
        pain = "Waiting forever for milk to warm is stressful on a trip."
        if "微波" in pains:
            pain = "Hunting for a microwave on the road is never easy."
        elif "不便携" in pains or "太大" in pains or "笨重" in pains:
            pain = "A bulky warmer does not fit your travel bag or airport routine."
        elif "热水" in pains or "没热水" in pains or "外出" in pains:
            pain = "No hot water when you are out — especially at the airport or on the road."
        sell = "This portable warmer heats evenly in minutes."
        if "充电" in selling or "USB" in selling.upper():
            sell = "USB-C rechargeable — warm milk wherever you travel."
        elif "便携" in selling:
            sell = "Compact and travel-ready — warm milk at the airport or on the go."
        proof = "Rechargeable, compact, and easy to pack in your bag."
        return [hook, pain, sell, proof, profile.get("cta", "")]

    if sid == "outdoor":
        hook = "Hard to warm a bottle at the park?"
        pain = "Outdoor feeds should not mean cold milk or long waits."
        sell = "Portable heating that keeps up with your park day."
        proof = "Small enough for the diaper bag, ready at the bench."
        return [hook, pain, sell, proof, profile.get("cta", "")]

    if sid == "office":
        hook = "Need warm milk fast between meetings?"
        pain = "Workdays leave little time for slow bottle prep."
        sell = "Quick, even heating at your desk."
        proof = "Discreet setup that fits a busy work routine."
        return [hook, pain, sell, proof, profile.get("cta", "")]

    if sid == "public":
        hook = "Dining out and bottle prep gets stressful?"
        pain = "No one wants a long wait when baby is hungry at the mall."
        sell = "Warm milk quietly at the table in minutes."
        proof = "Compact enough to use discreetly while you are out."
        return [hook, pain, sell, proof, profile.get("cta", "")]

    return [
        "Need a better way to warm milk?",
        "The old routine is slower than it should be.",
        "This portable warmer heats evenly in minutes.",
        f"Made for {profile.get('en', 'daily feeding')}.",
        profile.get("cta", "Save this for your routine."),
    ]


def pump_voiceovers(market: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    pains = _blob(market.get("pain_tags") or [])
    selling = _blob(market.get("selling_tags") or [])
    sid = profile["id"]
    if sid == "bedroom":
        hook = "Night pumping should not be this uncomfortable."
        if "疼" in pains or "不适" in pains:
            hook = "Pumping at night should not hurt — but the wrong fit often does."
        pain = "Wrong fit makes every middle-of-the-night session harder."
        sell = "Quieter motor and better fit for night sessions."
        if "护罩" in selling or "尺寸" in selling:
            sell = "Multiple flange sizes help you find a better fit at night."
        proof = "Easier cleanup when you are half asleep."
        return [hook, pain, sell, proof, profile.get("cta", "Save this for your next night session.")]
    return [
        "Still struggling with your pump setup?",
        "Wrong fit can make every session uncomfortable.",
        "Adjustable suction and easy-clean parts save time.",
        f"Built for {profile.get('en', 'daily pumping')}.",
        profile.get("cta", "Save this for your next pumping session."),
    ]


def shot_specs(
    *,
    profile: dict[str, Any],
    market: dict[str, Any],
    voiceovers: list[str],
) -> list[tuple[str, str, str, str, str]]:
    scene = profile["primary_tag"]
    pains = _blob(market.get("pain_tags") or [])
    selling = _blob(market.get("selling_tags") or [])
    vos = voiceovers
    return [
        ("钩子", "0-3s", f"{scene}：近景口播/问题特写", vos[0], default_footage_for_role("钩子")),
        ("痛点", "3-8s", f"{scene}：呈现痛点（{pains}）", vos[1], default_footage_for_role("痛点")),
        ("方案", "8-13s", f"{scene}：储奶袋/家用奶瓶经翻盖倒入杯内加热，倾斜经盖面圆孔出液嘴倒入干净奶瓶（{selling}；{THERMOS_USAGE_ZH}）", vos[2], default_footage_for_role("方案")),
        ("证明", "13-17s", f"{scene}：效果/细节证明", vos[3], default_footage_for_role("证明")),
        ("行动号召", "17-20s", f"{scene}：口播对镜收束", vos[4], default_footage_for_role("行动号召")),
    ]


def build_storyboard(
    *,
    product_name: str,
    market: dict[str, Any],
    profile: dict[str, Any],
    voiceovers: list[str],
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    audience = _blob(market.get("audience_tags") or [])
    scene = profile["primary_tag"]
    character = resolve_character(market)
    specs = shot_specs(profile=profile, market=market, voiceovers=voiceovers)
    storyboard: list[dict[str, Any]] = []
    subtitle_copy: list[str] = []
    visual_prompts: list[str] = []
    seedance_prompts: list[str] = []

    for i, (role, timing, visual, vo, ft) in enumerate(specs, start=1):
        vp = (
            f"{visual}；产品：{product_name}；人群：{audience}；"
            f"场景：{scene}（全片统一，禁止混入其他场景）；{THERMOS_VISUAL_RULES_ZH}；竖屏9:16"
        )
        sd = ""
        if ft in ("AI_BROLL", "AI_VIDEO"):
            sd = build_role_video_prompt(role, profile, product_name, vo, character=character)
            seedance_prompts.append(sd)
        storyboard.append({
            "number": i,
            "role": role,
            "timing": timing,
            "visual": visual,
            "voiceover_en": vo,
            "subtitle_en": vo,
            "visual_prompt": vp,
            "seedance_prompt": sd,
            "footage_type": ft,
            "camera_motion": default_camera_motion(role),
        })
        subtitle_copy.append(vo)
        visual_prompts.append(vp)

    return storyboard, subtitle_copy, visual_prompts, seedance_prompts


def _forbidden_scene_tokens(profile: dict[str, Any]) -> list[str]:
    """其他场景组的中文关键词，用于从画面描述中剔除冲突场景。"""
    current_id = profile.get("id")
    tokens: list[str] = []
    for scene in SCENE_DEFS:
        if scene["id"] == current_id:
            continue
        tokens.append(str(scene.get("zh") or ""))
        tokens.extend(str(k) for k in scene.get("match") or ())
    out: list[str] = []
    for t in tokens:
        t = t.strip()
        if t and t not in out:
            out.append(t)
    return out


def _strip_foreign_scenes(text: str, forbidden: list[str], primary: str) -> str:
    out = text or ""
    for token in forbidden:
        if not token or token == primary:
            continue
        out = out.replace(token, primary)
    return out


def align_pack_to_market_tags(
    pack: dict[str, Any],
    *,
    market: dict[str, Any],
    product_name: str,
) -> dict[str, Any]:
    """将用户勾选的人群/场景/卖点/痛点统一写入分镜，避免 LLM 或旧脚本残留其他场景。"""
    audience_tags = [str(t).strip() for t in (market.get("audience_tags") or []) if str(t).strip()]
    scenario_tags = [str(t).strip() for t in (market.get("scenario_tags") or []) if str(t).strip()]
    selling_tags = [str(t).strip() for t in (market.get("selling_tags") or []) if str(t).strip()]
    pain_tags = [str(t).strip() for t in (market.get("pain_tags") or []) if str(t).strip()]
    if not scenario_tags:
        return pack

    profile = resolve_scenario_profile(scenario_tags)
    primary = str(profile.get("primary_tag") or scenario_tags[0])
    audience = _blob(audience_tags)
    pains = _blob(pain_tags)
    selling = _blob(selling_tags)
    conflict = scenario_conflict_note(scenario_tags)
    forbidden = _forbidden_scene_tokens(profile)

    inputs = pack.setdefault("inputs", {})
    inputs["market"] = {
        **(inputs.get("market") if isinstance(inputs.get("market"), dict) else {}),
        **market,
        "audience_tags": audience_tags,
        "scenario_tags": scenario_tags,
        "selling_tags": selling_tags,
        "pain_tags": pain_tags,
    }
    inputs["scenario_profile"] = profile.get("id")
    inputs["scenario_primary"] = primary
    inputs["scenario_conflict_note"] = conflict
    inputs["personalization"] = {
        "audience_tags": audience_tags,
        "scenario_tags": scenario_tags,
        "selling_tags": selling_tags,
        "pain_tags": pain_tags,
        "primary_scene": primary,
    }
    pack["personalization_summary"] = " · ".join(
        x for x in (
            f"人群：{audience}" if audience else "",
            f"场景：{primary}" if primary else "",
            f"卖点：{selling}" if selling else "",
            f"痛点：{pains}" if pains else "",
        ) if x
    )

    role_visual = {
        "钩子": f"{primary}：近景口播/问题特写",
        "痛点": f"{primary}：呈现痛点（{pains or '用户所选痛点'}）",
        "方案": f"{primary}：储奶袋/家用奶瓶经翻盖倒入杯内加热，倾斜经盖面圆孔出液嘴倒入干净奶瓶（{selling or '用户所选卖点'}；{THERMOS_USAGE_ZH}）",
        "证明": f"{primary}：效果/细节证明",
        "行动号召": f"{primary}：口播对镜收束",
    }

    storyboard = pack.get("storyboard") or []
    for shot in storyboard:
        ensure_shot_camera_motion(shot)
        role = str(shot.get("role") or "").strip()
        if role in role_visual:
            shot["visual"] = role_visual[role]
        else:
            shot["visual"] = _strip_foreign_scenes(str(shot.get("visual") or ""), forbidden, primary)
            if primary not in shot["visual"]:
                shot["visual"] = f"{primary}：{shot['visual']}" if shot["visual"] else f"{primary}：产品展示"

        anchor_bits = [f"产品：{product_name}", f"人群：{audience}", f"场景：{primary}（全片统一，禁止混入其他场景）"]
        if role == "痛点" and pains:
            anchor_bits.append(f"痛点锚点：{pains}")
        if role == "方案" and selling:
            anchor_bits.append(f"卖点锚点：{selling}")
        anchor = "；".join(anchor_bits)

        vp = _strip_foreign_scenes(str(shot.get("visual_prompt") or ""), forbidden, primary)
        if primary not in vp or "人群：" not in vp or "场景：" not in vp:
            vp = f"{shot.get('visual', '')}；{anchor}；{THERMOS_VISUAL_RULES_ZH}；竖屏9:16"
        else:
            if role == "痛点" and pains and pains not in vp:
                vp = f"{vp}；痛点锚点：{pains}"
            if role == "方案" and selling and selling not in vp:
                vp = f"{vp}；卖点锚点：{selling}"
        shot["visual_prompt"] = vp

        sd = str(shot.get("seedance_prompt") or "")
        if sd:
            shot["seedance_prompt"] = _strip_foreign_scenes(sd, forbidden, primary)

    if storyboard:
        pack["visual_prompts"] = [str(s.get("visual_prompt") or "") for s in storyboard]
        pack["seedance_prompts"] = [
            str(s.get("seedance_prompt") or "")
            for s in storyboard
            if s.get("footage_type") in ("AI_BROLL", "AI_VIDEO") and s.get("seedance_prompt")
        ]
    return pack
