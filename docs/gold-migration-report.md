# Gold Migration Report

Date: 2026-07-13

## Source

Requested upstream:

- `https://github.com/zmq18560817115-eng/-Overseas-Video-Localization-Workflow.git`

GitHub access from this machine failed during this run:

- Global git proxy pointed to `http://127.0.0.1:7890`, but the local proxy was not reachable.
- A direct `git ls-remote` attempt also timed out with curl 28.

Fallback source used:

- `C:\Users\bu\Documents\海外视频本地化工作流`
- Source git commit: `6e55885b`
- Source remote `workflow`: `https://github.com/zmq18560817115-eng/-Overseas-Video-Localization-Workflow.git`

The copied source paths had no uncommitted changes at migration time.

## Copied Items

| Source | Target | Status |
| --- | --- | --- |
| `海外视频本地化MVP/app/scene_script.py` | `knowledge/legacy/scene_script.py` | copied |
| `海外视频本地化MVP/app/camera_motion.py` | `libshared/camera_motion.py` | copied |
| `海外视频本地化MVP/app/product_assets.py` | `knowledge/legacy/product_assets.py` | copied |
| `海外视频本地化MVP/app/feedback_loop.py` | `knowledge/legacy/feedback_loop.py` | copied |
| `overseas-loc-mvp/app/hero_frames.py` | `knowledge/legacy/hero_frames.py` | copied |
| `overseas-loc-mvp/app/ai_video.py` | `knowledge/legacy/ai_video.py` | copied |
| `overseas-loc-mvp/app/video_assemble.py` | `knowledge/legacy/video_assemble.py` | copied |
| `overseas-loc-mvp/app/video_enhance.py` | `knowledge/legacy/video_enhance.py` | copied |
| `overseas-video-output-standards/` | `knowledge/output-standards/` | copied |
| `01_素材库/产品资料/` | `data/01_素材库/产品资料/` | copied |
| `01_素材库/人像角色/` | `data/01_素材库/人像角色/` | copied |
| `05_反馈库/` | `data/05_反馈库/` | copied |
| `tiktok_collector/models.py` | `knowledge/legacy/tiktok_collector/models.py` | copied |
| `tiktok_collector/db.py` | `knowledge/legacy/tiktok_collector/db.py` | copied |
| `tiktok_collector/repository.py` | `knowledge/legacy/tiktok_collector/repository.py` | copied |
| `tiktok_collector/exporters.py` | `knowledge/legacy/tiktok_collector/exporters.py` | copied |

## Explicitly Excluded

- `tiktok_collector/scraper.py`
- `tiktok_collector/data/`
- `01_素材库/竞品对标/`
- root `.cmd` files
- old `web/app.js`
- MySQL launch scripts and runtime state
- venv/runtime/cache directories

## Verification

- All copied checklist targets exist.
- `knowledge/legacy/tiktok_collector/scraper.py` does not exist.
- `knowledge/legacy/tiktok_collector/data/` does not exist.
- `data/01_素材库/竞品对标/` does not exist.
- Data counts after migration:
  - `knowledge/output-standards/`: 6 files
  - `data/01_素材库/产品资料/`: 19 files
  - `data/01_素材库/人像角色/`: 7 files
  - `data/05_反馈库/`: 25 files
