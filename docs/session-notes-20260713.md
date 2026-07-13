# 会话记录 · 2026-07-13

## 一、项目终局目标

七 Agent 视频生产系统（`docs/绿地搭建执行手册v2.md`），从 0 新建仓库。验收标准是
**A8：真实素材连续产出 10 条合格成片**，达成后旧系统才允许下线；未达成前旧系统继续
冻结运行。

## 二、当前所处阶段

- 块 0～块 8（骨架、队列、检查点、九份 artifact 契约、工具层、引擎、API+工作台、
  采集+macOS 部署、10 视频切换验收）**代码骨架已全部完成**；另外还多做了
  product-library 只读索引和 ark/doubao/seedance 真实 provider 接入。
- `scripts/accept/report_10videos.md` 现状：**mock 模式 10/10 PASS**；真实模式
  `readiness: blocked`，缺 `DOUBAO_API_KEY`、`SEEDANCE_API_KEY` 两个环境变量——
  这是当前唯一的"真实切换"阻塞项。

## 三、本次会话完成的工作（已推送，PR #1 待合并）

PR: https://github.com/zmq18560817115-eng/shippin-agent/pull/1
（`claude/project-docs-review-m83unp` → `master`，open / clean / 无 CI 配置 /
无人 review）

四个修复，pytest 62 项全绿（含 A1-A8），三个独立 commit：

1. **cost_entries 表结构对齐**（commit `fix: cost_entries schema align + real pricing`）
   - 表结构改为 `entry_id/project_id/task_id/agent/tool/operation/phase/amount_cny/meta_json/created_at`。
   - 写了幂等迁移脚本 `orchestrator/queue.py:_migrate_cost_entries`（检测旧结构 →
     重建表 → 搬数据，二次运行是 no-op，不丢历史记账数据）。
   - 豆包工具（analyze/script/shotplan/review）真实调用按 usage tokens ×
     `config/orchestrator.yaml` 单价计费；SeedDance 按单镜固定价计费。之前
     pricing 全是 `null`，导致所有真实调用记账金额恒为 0——现已修复，用模拟真实
     HTTP 响应验证过 SELECT 结果非零（doubao 与 seedance 均非零）。
   - `config/orchestrator.yaml` 里的单价是从公开定价页估算的占位值，标注了需要
     用真实账单校准。

2. **检查点状态枚举统一**（commit `fix: checkpoint status enum`）
   - 检查点文件状态 `succeeded` → `completed`，对齐手册枚举；读取时兼容旧值
     （`checkpoint.DONE_STATUSES`）。
   - 任务/项目 DB 的 status 枚举（`queued/running/.../succeeded/...`）是另一套
     独立且本来就正确的枚举，未改动。

3. **宽高比链路修复**（commit `fix: aspect ratio propagation + real qa check`）
   - 根因：`ark.create_seedance_video` 请求体里根本没有传 `ratio`/`resolution`
     字段，只有 `model`+`content`，导致模型按参考图（方形白底图）默认出方形——
     这就是真实成片变成 960x960 的原因。
   - 已修：`shot_plan.aspect_ratio` → `seedance_shot` → `ark.create_seedance_video`
     全链路打通，请求体现在带 `ratio`/`resolution`/`duration`。
   - `final_qa.resolution_matches_aspect` 之前是硬编码 `True` 的空壳；现在是真实
     ffprobe 校验，不匹配会让任务 `failed`，不再放行到 archive。
   - 回归测试复现了原始 bug 场景：`_resolution_matches_aspect("960x960", "9:16")
     is False`，`_resolution_matches_aspect("1080x1920", "9:16") is True`。

4. **回归自证** — 新增 `tests/test_cost_migration.py`、`tests/test_real_pricing.py`、
   `tests/test_aspect_ratio.py`，`python -m pytest -q` 62 passed。

禁区确认未破坏：`schemas/` 必填字段未动、`knowledge/legacy/product_assets.py`
白底主图校验未动、未提交 `.env`/`db/`/`data/runs`。

## 四、距离目标还差什么

| 缺口 | 说明 |
|---|---|
| 真实 API Key | 没有 `DOUBAO_API_KEY`/`SEEDANCE_API_KEY`，无法做真实冒烟测试，pricing 是估算占位值，需要真实账单校准 |
| 真实 A8 十条成片 | 手册要求的"连续产出 10 条合格成片"从未真实跑过，只跑过 mock |
| PR #1 未合并 | 需要 review 后合并进 master |
| 本地开发环境两个阻塞 | ① 本地 venv 缺依赖（已在本次会话中通过 `pip install -r requirements.txt` 解决）；② 本地 git 代理配置指向 `127.0.0.1:443` 但代理未运行，导致 `git fetch` 连不上 GitHub——**这个还没确认解决**，卡在拉取 PR 分支这一步 |

## 五、明天建议的顺序

1. **先解决本地代理问题**：检查 `git config --global --get http.proxy` /
   `https.proxy` 的输出，要么启动对应代理软件，要么 `--unset` 掉改为直连；然后
   `git fetch origin claude/project-docs-review-m83unp` +
   `git checkout claude/project-docs-review-m83unp`，本地跑一遍
   `python -m pytest -v` 亲眼确认全绿。
2. **申请/配置真实 `DOUBAO_API_KEY` 和 `SEEDANCE_API_KEY`**，跑一次真实（非
   mock）冒烟，记录真实账单，回填校准 `config/orchestrator.yaml` 里的 pricing
   占位值。
3. **Review 并合并 PR #1**。
4. 具备真实 key 之后，才谈得上推进真正的 A8：连续真实产出 10 条合格成片。
