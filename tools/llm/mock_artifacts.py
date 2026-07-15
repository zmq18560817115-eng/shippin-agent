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
                "voiceover_en": "Night feeds should feel easier.",
                "voiceover_zh": "夜间喂养准备，可以更轻松。",
                "scene_zh": "深夜卧室，暖黄色床头灯，床头柜上有恒温杯、干净奶瓶与喂养用品；同一位照护者穿浅色家居服。",
                "action_zh": "照护者轻放恒温杯到床头柜，建立夜间喂养准备情境。",
                "story_beat_zh": "从真实夜间场景切入，让观众识别熟悉的准备时刻。",
                "subtitle_en": "Night feeds should feel easier.",
                "selling_points": [],
            },
            {
                "number": 2,
                "role": "痛点",
                "timing": "6-12s",
                "voiceover_en": "Cold milk and long waits make bedtime harder.",
                "voiceover_zh": "奶液变冷和漫长等待，会让睡前准备更困难。",
                "scene_zh": "保持同一卧室、暖光和床头柜，等待中的奶瓶位于画面内。",
                "action_zh": "照护者看向等待中的奶液与奶瓶，短暂停顿后开始准备。",
                "story_beat_zh": "将麻烦具体化，为解决方案出现建立动机。",
                "subtitle_en": "Cold milk and long waits make bedtime harder.",
                "selling_points": [],
            },
            {
                "number": 3,
                "role": "方案",
                "timing": "12-18s",
                "voiceover_en": "Pour milk into the cup and warm it for bottle prep.",
                "voiceover_zh": "将奶液倒入恒温杯，准备好后再倒入干净奶瓶。",
                "scene_zh": "同一床头柜台面，恒温杯与独立的干净奶瓶并排；产品外观匹配已批准身份图。",
                "action_zh": "将允许的奶液倒入恒温杯，准备后经出液口倒入独立奶瓶；禁止将奶瓶插入杯中。",
                "story_beat_zh": "产品作为解决方案进入，完成正确且可见的使用流程。",
                "subtitle_en": "Pour milk into the cup and warm it for bottle prep.",
                "selling_points": ["USB-C rechargeable"],
            },
            {
                "number": 4,
                "role": "证明",
                "timing": "18-24s",
                "voiceover_en": "The compact cup fits your nightstand or bag.",
                "voiceover_zh": "小巧机身，适合放在床头或随身包中。",
                "scene_zh": "床头柜细节转到同一照护者的随身包，光线、服装与产品外观保持一致。",
                "action_zh": "展示产品放入床头柜抽屉或随身包；若显示温度，只能显示 98 华氏度。",
                "story_beat_zh": "通过收纳细节证明产品适配场景，而不是重复口播卖点。",
                "subtitle_en": "The compact cup fits your nightstand or bag.",
                "selling_points": ["portable"],
            },
            {
                "number": 5,
                "role": "行动号召",
                "timing": "24-30s",
                "voiceover_en": "Save this for your next night feed.",
                "voiceover_zh": "为下一次夜间喂养先收藏这条。",
                "scene_zh": "回到整洁的床头柜全景，准备完成的奶瓶与恒温杯位于同一画面。",
                "action_zh": "照护者收好物品，镜头停留在产品与准备完成的奶瓶上。",
                "story_beat_zh": "从混乱回到有序，以低压力行动号召完成收束。",
                "subtitle_en": "Save this for your next night feed.",
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
        visual = f"{role} shot with product-safe composition."
        visual_prompt = f"{role} scene, product remains anchored to approved material."
        if number == 4:
            visual = (
                "Close-up: tilt the warming cup and pour through the round spout "
                "into the separate clean baby bottle; show 98 F only if legible."
            )
            visual_prompt = visual
        shots.append(
            {
                "number": number,
                "visual": visual,
                "visual_prompt": visual_prompt,
                "seedance_prompt": (
                    "Continuity lock: same location, lighting, caregiver, wardrobe, hands, and props across all five shots. "
                    "Product appearance must match the white-background hero reference. "
                    "The warming cup and baby bottle are separate products; never insert or attach the bottle to the cup. "
                    "If visible, the display reads 98 degrees Fahrenheit (98 F), never Celsius. "
                    "Use scenario and detail references only as prompt guidance. "
                    f"Shot role: {role}. Voiceover: {section['voiceover_en']}"
                ),
                "visual_zh": "请在真实生成时查看场景、动作和产品外观。",
                "seedance_prompt_zh": "连续性锁定：同一场景、人物、产品外观与道具；仅作为中文审核提示。",
                "footage_type": "AI_VIDEO" if role in {"方案", "证明", "行动号召"} else "AI_BROLL",
                "camera_motion": {
                    "type": "dolly_in" if number == 1 else "static",
                    "duration_sec": 6,
                },
            }
        )
    return {
        "version": "2.0",
        "project_id": project_id,
        "script_copy_ref": "artifacts/script_copy.json",
        "aspect_ratio": "9:16",
        "shots": shots,
    }
