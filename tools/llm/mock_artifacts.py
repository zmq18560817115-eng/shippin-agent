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
                "subtitle_en": "Night feeds should feel easier.",
                "selling_points": [],
            },
            {
                "number": 2,
                "role": "痛点",
                "timing": "6-12s",
                "voiceover_en": "Cold milk and long waits make bedtime harder.",
                "subtitle_en": "Cold milk and long waits make bedtime harder.",
                "selling_points": [],
            },
            {
                "number": 3,
                "role": "方案",
                "timing": "12-18s",
                "voiceover_en": "Pour milk into the cup and warm it for bottle prep.",
                "subtitle_en": "Pour milk into the cup and warm it for bottle prep.",
                "selling_points": ["USB-C rechargeable"],
            },
            {
                "number": 4,
                "role": "证明",
                "timing": "18-24s",
                "voiceover_en": "The compact cup fits your nightstand or bag.",
                "subtitle_en": "The compact cup fits your nightstand or bag.",
                "selling_points": ["portable"],
            },
            {
                "number": 5,
                "role": "行动号召",
                "timing": "24-30s",
                "voiceover_en": "Save this for your next night feed.",
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
        shots.append(
            {
                "number": number,
                "visual": f"{role} shot with product-safe composition.",
                "visual_prompt": f"{role} scene, product remains anchored to approved material.",
                "seedance_prompt": (
                    "Product appearance must match the white-background hero reference. "
                    "Use scenario and detail references only as prompt guidance. "
                    f"Shot role: {role}. Voiceover: {section['voiceover_en']}"
                ),
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
