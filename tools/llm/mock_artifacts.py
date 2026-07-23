from __future__ import annotations

from typing import Any


def mock_script_copy(
    project_id: str,
    product_id: str = "便携恒温杯",
    *,
    provider: str = "doubao",
    creative_request: str = "",
) -> dict[str, Any]:
    if not _is_warming_product(product_id, creative_request):
        return _generic_script_copy(project_id, product_id, provider=provider, creative_request=creative_request)
    profile = _creative_profile(creative_request)
    place = profile["place"]
    audience = profile["audience"]
    opening = profile["opening"]
    pressure = profile["pressure"]
    cta = profile["cta"]
    return {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product_id,
        "source_link_id": None,
        "total_duration_s": 30,
        "generator": {
            "provider": provider,
            "model": "mock",
            "prompt_version": "input-aware-mock-v1",
        },
        "creative_request": creative_request.strip(),
        "sections": [
            {
                "number": 1,
                "role": "钩子",
                "timing": "0-6s",
                "voiceover_zh": opening,
                "scene_zh": f"{place}，{profile['light']}，恒温杯、独立干净奶瓶与随身喂养用品清晰分开；同一位{audience}保持服装和随身物品一致。",
                "action_zh": profile["opening_action"],
                "story_beat_zh": f"从{profile['context']}的未完成动作切入，让目标受众立即识别自己的使用时刻。",
                "subtitle_zh": opening,
                "selling_points": [],
            },
            {
                "number": 2,
                "role": "痛点",
                "timing": "6-12s",
                "voiceover_zh": pressure,
                "scene_zh": f"保持同一{place}、光线和人物状态，等待中的独立奶瓶与时间压力同时进入画面。",
                "action_zh": profile["pressure_action"],
                "story_beat_zh": "将麻烦具体化，为解决方案出现建立动机。",
                "subtitle_zh": pressure,
                "selling_points": [],
            },
            {
                "number": 3,
                "role": "方案",
                "timing": "12-18s",
                "voiceover_zh": f"在{profile['context']}，先把允许的奶液来源倒入恒温杯。",
                "scene_zh": f"同一{place}的稳定台面，恒温杯与独立干净奶瓶并排，产品外观匹配已批准身份图。",
                "action_zh": "将允许的奶液来源倒入恒温杯；本镜不出现向奶瓶倒液。",
                "story_beat_zh": "产品作为解决方案进入，先完成正确使用流程的第一步。",
                "subtitle_zh": f"在{profile['context']}，先把允许的奶液来源倒入恒温杯。",
                "selling_points": ["USB-C rechargeable"],
            },
            {
                "number": 4,
                "role": "证明",
                "timing": "18-24s",
                "voiceover_zh": "准备完成后，经圆形出液口倒入独立的干净奶瓶。",
                "scene_zh": f"保持同一{place}、人物、服装与光线，恒温杯和独立奶瓶清晰可见。",
                "action_zh": "保持主盖闭合，倾斜恒温杯，让奶液从圆形出液口连续倒入独立的干净奶瓶；禁止反向倒液或把奶瓶放入杯中。",
                "story_beat_zh": "完成正确使用流程的第二步，用可见动作证明方案可执行。",
                "subtitle_zh": "准备完成后，经圆形出液口倒入独立的干净奶瓶。",
                "selling_points": ["portable"],
            },
            {
                "number": 5,
                "role": "行动号召",
                "timing": "24-30s",
                "voiceover_zh": cta,
                "scene_zh": f"回到整洁的{place}全景，准备完成的独立奶瓶与恒温杯位于同一画面。",
                "action_zh": "照护者收好物品，镜头停留在产品与准备完成的奶瓶上。",
                "story_beat_zh": "从混乱回到有序，以低压力行动号召完成收束。",
                "subtitle_zh": cta,
                "selling_points": [],
            },
        ],
        "feedback_constraints_applied": [],
    }


def _is_warming_product(product_id: str, request: str) -> bool:
    normalized = f"{product_id} {request}".casefold()
    return any(token in normalized for token in ("恒温杯", "温奶", "warming cup", "bottle warmer"))


def _generic_script_copy(
    project_id: str,
    product_id: str,
    *,
    provider: str,
    creative_request: str,
) -> dict[str, Any]:
    product = product_id.strip() or "当前主题"
    profile = _creative_profile(creative_request)
    roles = ("钩子", "痛点", "方案", "证明", "行动号召")
    timings = ("0-6s", "6-12s", "12-18s", "18-24s", "24-30s")
    voiceovers = (
        f"真正让人停下来的，不是口号，而是{product}正在解决的那个具体瞬间。",
        "先让问题发生在真实生活里，观众才会在画面中认出自己。",
        f"这时再让{product}进入画面，用一个清楚动作回应刚才的困扰。",
        "不堆参数，只用使用前后的变化证明价值。",
        "如果这个场景也属于你，先把这条思路收藏下来。",
    )
    actions = (
        "人物停下一个尚未完成的动作，视线落向问题发生的位置。",
        "人物尝试继续原动作，但被具体障碍打断。",
        f"人物拿起{product}并完成一个与用户需求直接相关的主要动作。",
        f"镜头贴近动作结果，清楚保留{product}与使用环境的关系。",
        "人物完成原先被打断的事情，产品留在自然使用位置。",
    )
    sections = []
    for index, (role, timing, voiceover, action) in enumerate(zip(roles, timings, voiceovers, actions), start=1):
        sections.append({
            "number": index,
            "role": role,
            "timing": timing,
            "voiceover_zh": voiceover,
            "scene_zh": f"{profile['place']}，{profile['light']}；同一人物、服装和主要道具保持连续，围绕用户输入的真实情境展开。",
            "action_zh": action,
            "story_beat_zh": (
                "人物开始一个尚未完成的动作，为下一段问题出现留下悬念" if index == 1 else
                "现实阻碍打断人物原本节奏，让产品介入具备明确原因" if index == 2 else
                "产品通过一个可见动作回应困扰，推动人物继续完成目标" if index == 3 else
                "使用前后的可见变化形成证据，消除观众对效果的疑问" if index == 4 else
                "人物顺利完成原定目标，以自然行动收束并给出下一步"
            ),
            "subtitle_zh": voiceover,
            "selling_points": [],
        })
    return {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product,
        "source_link_id": None,
        "total_duration_s": 30,
        "generator": {"provider": provider, "model": "mock", "prompt_version": "generic-input-aware-mock-v1"},
        "creative_request": creative_request.strip(),
        "sections": sections,
        "feedback_constraints_applied": [],
    }


def _creative_profile(request: str) -> dict[str, str]:
    text = " ".join(request.strip().split())
    if any(token in text for token in ("旅行", "旅途", "出行", "机场", "高铁", "酒店", "车内")):
        return {
            "place": "明亮的高铁候车区行李整理台",
            "light": "自然窗光与柔和顶灯",
            "audience": "准备出行的新手照护者",
            "context": "旅途中",
            "opening": "行程已经开始，喂养准备别再临时找办法。",
            "opening_action": "照护者一手扶住行李，一手从侧袋取出恒温杯，身后的登车提示即将变化。",
            "pressure": "空间有限、时间在走，奶液准备更需要清楚的顺序。",
            "pressure_action": "照护者看一眼登车时间，再把奶液来源、恒温杯和独立奶瓶依次排开。",
            "cta": "下次带宝宝出发前，把这套准备顺序存下来。",
        }
    if any(token in text for token in ("办公室", "办公", "通勤", "工位", "午休")):
        return {
            "place": "安静的办公室母婴室操作台",
            "light": "午后自然光与中性顶灯",
            "audience": "需要兼顾工作的通勤照护者",
            "context": "工作间隙",
            "opening": "午休只剩十分钟，准备动作不能再绕远。",
            "opening_action": "照护者放下工牌和手机，把恒温杯从通勤包中取出并腾出操作台。",
            "pressure": "会议时间在靠近，反复等待会打乱整个下午。",
            "pressure_action": "照护者看向手机日程，随后按使用顺序摆好奶液来源与独立奶瓶。",
            "cta": "把这套工作日准备流程留给下一次忙碌午后。",
        }
    if any(token in text for token in ("露营", "户外", "公园", "野餐")):
        return {
            "place": "有遮阳棚的公园野餐桌",
            "light": "柔和日光与树影",
            "audience": "喜欢带宝宝户外活动的照护者",
            "context": "户外停留时",
            "opening": "风景可以慢慢看，喂养准备要先安排好。",
            "opening_action": "照护者压住被风吹动的野餐布，从收纳包中取出恒温杯。",
            "pressure": "户外台面有限，步骤越混乱越容易手忙脚乱。",
            "pressure_action": "照护者整理台面，将奶液来源、恒温杯和独立奶瓶按顺序摆放。",
            "cta": "下次去户外前，把这套准备清单一起带上。",
        }
    return {
        "place": "深夜卧室床头柜",
        "light": "暖黄色床头灯",
        "audience": "夜间喂养照护者",
        "context": "夜间喂养时",
        "opening": "夜里醒来的那一刻，准备流程越清楚越从容。",
        "opening_action": "照护者轻放恒温杯到床头柜，伸手整理独立奶瓶与喂养用品。",
        "pressure": "奶液变冷和漫长等待，会让睡前准备更困难。",
        "pressure_action": "照护者看向等待中的奶液与奶瓶，短暂停顿后开始准备。",
        "cta": "为下一次夜间喂养先收藏这套准备顺序。",
    }


def mock_shot_plan(project_id: str, script_copy: dict[str, Any]) -> dict[str, Any]:
    warming_product = _is_warming_product(
        str(script_copy.get("product_id") or ""),
        str(script_copy.get("creative_request") or ""),
    )
    shots = []
    for section in script_copy["sections"]:
        number = int(section["number"])
        role = section["role"]
        visual = " ".join(value for value in (section.get("scene_zh"), section.get("action_zh"), section.get("story_beat_zh")) if value)
        visual_prompt = f"{role}镜头。{visual} 产品外观严格锚定获批素材。"
        if warming_product and number == 4:
            visual = "近景展示恒温杯从圆形出液口向独立的干净奶瓶倒液；温度清晰可见时只能显示 98°F。"
            visual_prompt = visual
        shots.append(
            {
                "number": number,
                "visual": visual,
                "visual_prompt": visual_prompt,
                "seedance_prompt": (
                    "Continuity lock: same location, lighting, caregiver, wardrobe, hands, and props across all five shots. "
                    "Product appearance must match the white-background hero reference. "
                    + (
                        "Product identity lock: preserve the approved proportions, lid, ring, spout, display, button, and port cover. "
                        "The warming cup and baby bottle are separate products; never insert or attach the bottle to the cup. "
                        "If visible, the display reads 98 degrees Fahrenheit (98 F), never Celsius. "
                        if warming_product
                        else f"Product identity lock: keep {script_copy.get('product_id') or 'the product'} consistent with the supplied facts and references; do not invent specifications, labels, accessories, or usage steps. "
                    )
                    + "Use scenario and detail references only as prompt guidance. "
                    f"Action continuity for shot {number}: one motivated action that begins from the previous shot end state. "
                    f"Camera contract: shot {number} uses a distinct lens, framing, camera height, and restrained movement. "
                    "Negative constraints: no malformed hands, duplicated props, warped product, invented text, jump cuts, or continuity breaks. "
                    f"Shot role: {role}. Voiceover: {section.get('voiceover_zh', '')}. "
                    + ("Pour from the warming cup through the round spout into a separate clean baby bottle." if warming_product and number == 4 else "")
                ),
                "visual_zh": visual,
                "seedance_prompt_zh": (
                    "连续性锁定：同一场景、人物、服装、光线、产品外观与道具。"
                    + ("恒温杯与奶瓶保持独立，温度可见时只能显示 98 华氏度。" if warming_product else "不得补造未提供的产品结构、参数、文字或使用步骤。")
                    + visual_prompt
                ),
                "footage_type": "AI_VIDEO" if role in {"方案", "证明", "行动号召"} else "AI_BROLL",
                "camera_motion": {
                    "type": {
                        1: "dolly_in",
                        2: "static",
                        3: "pan_right",
                        4: "static",
                        5: "dolly_out",
                    }.get(number, "static"),
                    "duration_sec": 6,
                },
            }
        )
    return {
        "version": "2.0",
        "project_id": project_id,
        "script_copy_ref": "artifacts/script_copy.json",
        "aspect_ratio": "9:16",
        "scene_continuity": str(script_copy["sections"][0].get("scene_zh") or "同一生活场景与光线"),
        "character_continuity": "同一位成年照护者，保持身份、发型、服装、手部与体态一致",
        "shots": shots,
    }
