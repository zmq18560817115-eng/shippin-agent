from __future__ import annotations

from pathlib import Path

from tools.base_tool import ToolContext
from tools.providers import ark
from tools.video import seedance_shot


def test_seedance_prompt_has_shot_specific_action_contract() -> None:
    manifest = {"product_id": "便携恒温杯", "seedance_source": "白底主图.png"}
    intro = seedance_shot._shot_prompt({"number": 1, "visual_zh": "床头建立镜头"}, manifest)
    pour = seedance_shot._shot_prompt({"number": 4, "visual_zh": "闭盖后向奶瓶倒液"}, manifest)
    assert "must not contain pouring" in intro
    assert "main lid visibly closed" in pour
    assert "approved round spout" in pour


def test_prompt_only_seedance_prompt_does_not_inherit_warming_cup_rules() -> None:
    manifest = {
        "product_id": "折叠雨伞",
        "identity_mode": "prompt_only",
        "seedance_source": "",
    }

    prompt = seedance_shot._shot_prompt(
        {"number": 1, "visual_zh": "雨天街道上打开红色折叠雨伞"},
        manifest,
    )

    assert "雨天街道上打开红色折叠雨伞" in prompt
    assert "Do not introduce a warming cup" in prompt
    assert "98" not in prompt
    assert "Shot 1 must not contain pouring" not in prompt


def test_seedance_shot_forwards_additional_reference_paths(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_create(context, **kwargs):
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"video")
        return {"provider": "ark", "task_id": "task-1", "reference_count": 2}

    monkeypatch.setattr(seedance_shot.ark, "create_seedance_video", fake_create)
    result = seedance_shot.execute(
        {
            "project_id": "refs",
            "shot": {"number": 1, "reference_paths": ["usage.png"]},
            "asset_manifest": {
                "version": "2.0",
                "project_id": "refs",
                "product_id": "便携恒温杯",
                "seedance_source": "白底主图.png",
                "hero_frames": [{"number": 1, "path": "hero.png"}],
            },
        },
        ToolContext.from_mapping(
            {"mock": False, "run_root": str(tmp_path), "env": {"SEEDANCE_API_KEY": "configured"}}
        ),
    )
    assert result.ok
    assert captured["image_path"] == "白底主图.png"
    assert captured["image_paths"] == ["usage.png"]


def test_seedance_shot_does_not_leak_action_reference_to_unrelated_shot(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_create(context, **kwargs):
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"video")
        return {"provider": "ark", "task_id": "task-2", "reference_count": 2}

    monkeypatch.setattr(seedance_shot.ark, "create_seedance_video", fake_create)
    result = seedance_shot.execute(
        {
            "project_id": "manifest-refs",
            "shot": {"number": 1},
            "asset_manifest": {
                "version": "2.0",
                "project_id": "manifest-refs",
                "product_id": "便携恒温杯",
                "seedance_source": "白底主图.png",
                "reference_paths": ["倒出口参考.png"],
                "hero_frames": [{"number": 1, "path": "hero.png"}],
            },
        },
        ToolContext.from_mapping(
            {"mock": False, "run_root": str(tmp_path), "env": {"SEEDANCE_API_KEY": "configured"}}
        ),
    )
    assert result.ok
    assert captured["image_paths"] == []


def test_seedance_shot_routes_pour_reference_to_matching_shot(tmp_path: Path, monkeypatch) -> None:
    captured = {}

    def fake_create(context, **kwargs):
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"video")
        return {"provider": "ark", "task_id": "task-3", "reference_count": 2}

    monkeypatch.setattr(seedance_shot.ark, "create_seedance_video", fake_create)
    result = seedance_shot.execute(
        {
            "project_id": "pour-refs",
            "shot": {"number": 4, "visual_zh": "恒温杯从出液口向独立奶瓶倒液"},
            "asset_manifest": {
                "version": "2.0",
                "project_id": "pour-refs",
                "product_id": "便携恒温杯",
                "seedance_source": "白底主图.png",
                "reference_paths": ["倒出口参考.png"],
                "hero_frames": [{"number": 4, "path": "hero.png"}],
            },
        },
        ToolContext.from_mapping(
            {"mock": False, "run_root": str(tmp_path), "env": {"SEEDANCE_API_KEY": "configured"}}
        ),
    )
    assert result.ok
    assert captured["image_paths"] == ["倒出口参考.png"]


def test_seedance_request_marks_all_images_as_references(tmp_path: Path, monkeypatch) -> None:
    primary = tmp_path / "primary.png"
    usage = tmp_path / "usage.png"
    primary.write_bytes(b"primary")
    usage.write_bytes(b"usage")
    captured = {}

    def fake_post(url, *, api_key, body, timeout_s):
        captured.update(body)
        return {"id": "task-1"}

    monkeypatch.setattr(ark, "_post_json", fake_post)
    monkeypatch.setattr(
        ark,
        "_get_json",
        lambda *args, **kwargs: {
            "status": "succeeded",
            "video_url": "https://example.com/video.mp4",
        },
    )
    monkeypatch.setattr(
        ark,
        "_download",
        lambda url, output_path, timeout_s: output_path.write_bytes(b"video"),
    )
    monkeypatch.setattr(ark.time, "sleep", lambda _: None)

    ark.create_seedance_video(
        ToolContext.from_mapping(
            {
                "mock": False,
                "run_root": str(tmp_path),
                "env": {"SEEDANCE_API_KEY": "configured"},
            }
        ),
        prompt="Product demo",
        image_path=str(primary),
        image_paths=[str(usage)],
        output_path=tmp_path / "out.mp4",
    )

    images = [item for item in captured["content"] if item["type"] == "image_url"]
    assert len(images) == 2
    assert {item["role"] for item in images} == {"reference_image"}


def test_seedance_request_retries_without_image_role_on_model_validation_error(tmp_path: Path, monkeypatch) -> None:
    primary = tmp_path / "primary.png"
    primary.write_bytes(b"primary")
    requests = []

    def fake_post(url, *, api_key, body, timeout_s):
        requests.append(body)
        if len(requests) == 1:
            raise ark.ArkProviderError("Ark HTTP 400: image content role is invalid for this model")
        return {"id": "task-2"}

    monkeypatch.setattr(ark, "_post_json", fake_post)
    monkeypatch.setattr(
        ark,
        "_get_json",
        lambda *args, **kwargs: {"status": "succeeded", "video_url": "https://example.com/video.mp4"},
    )
    monkeypatch.setattr(ark, "_download", lambda url, output_path, timeout_s: output_path.write_bytes(b"video"))
    monkeypatch.setattr(ark.time, "sleep", lambda _: None)

    ark.create_seedance_video(
        ToolContext.from_mapping(
            {"mock": False, "run_root": str(tmp_path), "env": {"SEEDANCE_API_KEY": "configured"}}
        ),
        prompt="Product demo",
        image_path=str(primary),
        output_path=tmp_path / "out.mp4",
    )

    assert requests[0]["content"][1]["role"] == "reference_image"
    assert "role" not in requests[1]["content"][1]


def test_seedance_request_does_not_retry_non_role_errors(tmp_path: Path, monkeypatch) -> None:
    primary = tmp_path / "primary.png"
    primary.write_bytes(b"primary")
    calls = 0

    def fake_post(url, *, api_key, body, timeout_s):
        nonlocal calls
        calls += 1
        raise ark.ArkProviderError("Ark HTTP 429: quota exceeded")

    monkeypatch.setattr(ark, "_post_json", fake_post)
    try:
        ark.create_seedance_video(
            ToolContext.from_mapping(
                {"mock": False, "run_root": str(tmp_path), "env": {"SEEDANCE_API_KEY": "configured"}}
            ),
            prompt="Product demo",
            image_path=str(primary),
            output_path=tmp_path / "out.mp4",
        )
    except ark.ArkProviderError as exc:
        assert "quota" in str(exc)
    else:
        raise AssertionError("expected provider error")
    assert calls == 1
