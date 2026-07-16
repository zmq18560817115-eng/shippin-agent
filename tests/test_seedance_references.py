from __future__ import annotations

from pathlib import Path

from tools.base_tool import ToolContext
from tools.providers import ark
from tools.video import seedance_shot


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


def test_seedance_shot_uses_manifest_references_when_shot_has_none(tmp_path: Path, monkeypatch) -> None:
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
