from __future__ import annotations

from typing import Any


def mock_script_copy(project_id: str, product_id: str = "便携恒温杯", *, provider: str = "doubao") -> dict[str, Any]:
    return {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product_id,
        "source_link_id": None,
        "total_duration_s": 30,
        "generator": {
            "provider": provider,
            "model": "mock",
            "prompt_version": "block4-mock",
        },
        "sections": [
            {
                "number": 1,
                "role": "钩子",
                "timing": "0-6s",
                "voiceover_zh": "夜间喂养准备，可以更轻松。",
                "scene_zh": "深夜卧室，暖黄色床头灯，床头柜上有恒温杯、干净奶瓶与喂养用品；同一位照护者穿浅色家居服。",
                "action_zh": "照护者轻放恒温杯到床头柜，建立夜间喂养准备情境。",
                "story_beat_zh": "从真实夜间场景切入，让观众识别熟悉的准备时刻。",
                "subtitle_zh": "夜间喂养准备，可以更轻松。",
                "selling_points": [],
            },
            {
                "number": 2,
                "role": "痛点",
                "timing": "6-12s",
                "voiceover_zh": "奶液变冷和漫长等待，会让睡前准备更困难。",
                "scene_zh": "保持同一卧室、暖光和床头柜，等待中的奶瓶位于画面内。",
                "action_zh": "照护者看向等待中的奶液与奶瓶，短暂停顿后开始准备。",
                "story_beat_zh": "将麻烦具体化，为解决方案出现建立动机。",
                "subtitle_zh": "奶液变冷和漫长等待，会让睡前准备更困难。",
                "selling_points": [],
            },
            {
                "number": 3,
                "role": "方案",
                "timing": "12-18s",
                "voiceover_zh": "先将允许的奶液来源倒入恒温杯，开始准备。",
                "scene_zh": "同一床头柜台面，恒温杯与独立的干净奶瓶并排；产品外观匹配已批准身份图。",
                "action_zh": "将允许的奶液来源倒入恒温杯；本镜不出现向奶瓶倒液。",
                "story_beat_zh": "产品作为解决方案进入，先完成正确使用流程的第一步。",
                "subtitle_zh": "先将允许的奶液来源倒入恒温杯，开始准备。",
                "selling_points": ["USB-C rechargeable"],
            },
            {
                "number": 4,
                "role": "证明",
                "timing": "18-24s",
                "voiceover_zh": "准备完成后，经圆形出液口倒入独立的干净奶瓶。",
                "scene_zh": "保持同一床头柜、照护者、服装与灯光，恒温杯和独立奶瓶清晰可见。",
                "action_zh": "保持主盖闭合，倾斜恒温杯，让奶液从圆形出液口连续倒入独立的干净奶瓶；禁止反向倒液或把奶瓶放入杯中。",
                "story_beat_zh": "完成正确使用流程的第二步，用可见动作证明方案可执行。",
                "subtitle_zh": "准备完成后，经圆形出液口倒入独立的干净奶瓶。",
                "selling_points": ["portable"],
            },
            {
                "number": 5,
                "role": "行动号召",
                "timing": "24-30s",
                "voiceover_zh": "为下一次夜间喂养先收藏这条。",
                "scene_zh": "回到整洁的床头柜全景，准备完成的奶瓶与恒温杯位于同一画面。",
                "action_zh": "照护者收好物品，镜头停留在产品与准备完成的奶瓶上。",
                "story_beat_zh": "从混乱回到有序，以低压力行动号召完成收束。",
                "subtitle_zh": "为下一次夜间喂养先收藏这条。",
                "selling_points": [],
            },
        ],
        "feedback_constraints_applied": [],
    }


def mock_shot_plan(project_id: str, script_copy: dict[str, Any]) -> dict[str, Any]:
    shots = []
    for section in script_copy["sections"]:
        number = int(section["number"])
        role = section["role"]
        visual = " ".join(value for value in (section.get("scene_zh"), section.get("action_zh"), section.get("story_beat_zh")) if value)
        visual_prompt = f"{role}镜头。{visual} 产品外观严格锚定获批素材。"
        if number == 4:
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
                    "Product identity lock: preserve the approved proportions, lid, ring, spout, display, button, and port cover. "
                    "The warming cup and baby bottle are separate products; never insert or attach the bottle to the cup. "
                    "If visible, the display reads 98 degrees Fahrenheit (98 F), never Celsius. "
                    "Use scenario and detail references only as prompt guidance. "
                    f"Action continuity for shot {number}: one motivated action that begins from the previous shot end state. "
                    f"Camera contract: shot {number} uses a distinct lens, framing, camera height, and restrained movement. "
                    "Negative constraints: no malformed hands, duplicated props, warped product, invented text, jump cuts, or continuity breaks. "
                    f"Shot role: {role}. Voiceover: {section.get('voiceover_zh', '')}. "
                    + ("Pour from the warming cup through the round spout into a separate clean baby bottle." if number == 4 else "")
                ),
                "visual_zh": visual,
                "seedance_prompt_zh": "连续性锁定：同一场景、人物、服装、光线、产品外观与道具。" + visual_prompt,
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
        "scene_continuity": "同一深夜卧室、暖黄色床头灯与床头柜区域",
        "character_continuity": "同一位成年照护者，保持脸部身份、发型、浅色家居服、手部与体态一致",
        "shots": shots,
    }
