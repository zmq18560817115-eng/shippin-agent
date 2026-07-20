from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.video.ffmpeg_compose import _find_ffmpeg


def extract(manifest_path: Path, output_dir: Path) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg executable not found")
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for shot in manifest.get("shots") or []:
        number = int(shot.get("number") or 0)
        for take in shot.get("takes") or []:
            take_id = str(take.get("take_id") or "unknown").lower()
            source = Path(str(take.get("path") or ""))
            if not source.is_file():
                continue
            for second in (1, 3, 5):
                target = output_dir / f"shot-{number:02d}-take-{take_id}-{second}s.png"
                result = subprocess.run(
                    [ffmpeg, "-y", "-ss", str(second), "-i", source.as_posix(), "-frames:v", "1", target.as_posix()],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.returncode != 0 or not target.is_file():
                    raise RuntimeError(f"frame extraction failed for {source}: {result.stderr[-800:]}")
                frames.append(target)
    return frames


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract three review frames from every generated Take.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    for frame in extract(args.manifest, args.output_dir):
        print(frame.as_posix())
