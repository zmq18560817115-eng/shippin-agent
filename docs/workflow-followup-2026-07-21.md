# 工作流后续交接执行清单（2026-07-21）

本轮在 `claude/workflow-followup-dev-3pdyxd` 分支完成的代码/配置变更，以及需在真实
密钥与内网环境中由运维方执行的验收步骤。

## 本轮已完成（代码/配置，已随本分支提交）

### ① 更换模型 API 接口（模型版本号）
- 供应商与调用协议不变，仍为火山引擎 Ark（豆包文本 + Seedance 视频）。
- 默认模型版本升级：
  - 文本：`doubao-seed-1-8-251228` → `doubao-seed-2-1`
  - 视频：`doubao-seedance-2-0-fast-260128` → `doubao-seedance-2-0`
- 位置：`tools/providers/ark.py` 的 `DEFAULT_DOUBAO_MODEL` / `DEFAULT_SEEDANCE_MODEL`。
- 部署方可用 `ARK_DOUBAO_MODEL` / `ARK_SEEDANCE_MODEL` 覆盖为**确切的带日期端点 ID**
  （推荐在生产按供应商控制台的精确 ID 固定版本，避免别名解析歧义）。见 `.env.example`。

### ④ 预算模式（观察 → 强制）
- `pipeline_defs/viral-imitate.yaml` 的 `budget_mode` 由 `observe` 改为 `enforce`。
- 其余各处（项目创建默认、`config/orchestrator.yaml`、`schema.sql`、部署预检）本就为
  `enforce`，无需改动。
- 单价校准：`config/orchestrator.yaml` 中单价仍为**估算值**，注释已更新说明其尚未与
  `doubao-seed-2-1` / `doubao-seedance-2-0` 的真实账单对账。**上线后必须**用首月企业
  火山引擎账单，通过 `VAF_PRICE_<TOOL>_CNY` 覆盖校准（见下方步骤）。

### ③ 关键词相关性（后台只采相关视频）
- 已确认相关性过滤在代码中生效：`orchestrator/api.py::_collect_relevant_job_items`
  对每个候选调用 `tools/collect/relevance.py::score_item`，keyword 任务对
  `relevant == False`（分数 < 0.35）的条目跳过入库，不会“什么视频都采集”。
- account / trending 类型按设计不做关键词过滤（分数恒为 1.0）。
- 内网 Cookie / 限流 / 相关性稳定性属**运行期验证**，见下方运维步骤。

## 需运维方在真实环境执行（密钥/内网就绪后）

### 校准单价（配合 ④）
1. 跑通首条真实成片后，导出火山引擎账单中各模型实际扣费。
2. 用每次调用实测 token/时长换算单价，写入 `.env.local`：
   `VAF_PRICE_DOUBAO_ANALYZE_CNY` / `_SCRIPT_` / `_SHOTPLAN_` / `_REVIEW_` /
   `VAF_PRICE_SEEDANCE_SHOT_CNY`。
3. 重启后 `budget_mode=enforce` 会以校准后单价执行预算护栏。

### ② 真实豆包 + Seedance 30 秒成片验收
前置：`.env.local` 配好 `DOUBAO_API_KEY`、`SEEDANCE_API_KEY`，预算 `enforce` 且预算足够
覆盖五镜 + 至少一次重生（参考历史 ¥30+ 单片，建议 `budget_cny ≥ 40`）。
1. `python scripts/deployment_preflight.py --env-file .env.local` 全绿。
2. 真实模式创建项目，跑完 分析→脚本→脚本审核→分镜。
3. 逐镜生成 Take（每镜 ≥2 候选），过 `hero_gate`。
4. 逐镜人工抽帧质检，过 `take_gate`，合成 30 秒 720×1280 成片。
5. 保留：运行报告、五镜产物、最终成片、抽帧检查结果。

### ⑤ 真实成片抽帧目检（依赖 ②）
逐镜抽 1/3/5 秒帧，确认：
- 产品外观符合已批准素材，无虚构品牌 / Logo / 文字；
- 温标只出现 `98°F`，不得出现 `98°C` 或摄氏；
- 恒温杯与奶瓶独立，倒液方向正确（杯嘴 → 独立奶瓶）；
- 人物 / 服装 / 场景 / 产品在镜头间连续。
任一不合格 → 该镜重生，不得放行。

### ③ 内网后台采集稳定性验证
1. `.env.local` 设 `VAF_AUTO_COLLECT_ENABLED=true`、`VAF_AUTO_COLLECT_REAL=true`、
   `VAF_AUTO_COLLECT_TARGET_TYPE=keyword`、`VAF_AUTO_COLLECT_TARGET=<目标关键词>`，
   配好 `TIKTOK_COOKIES_FILE`（专用服务账号，勿提交）。
2. 持续运行数小时，观察后台采集进度：确认入库条目均与关键词相关（相关性分数），
   Cookie 未过期，限流触发时按退避重试而非崩溃。
3. 关键词检索精度不足时配置 `APIFY_API_TOKEN`，保留账号采集 / 人工直链为降级路径。

## 待明确 / 未处理

### ⑥ 清理无法恢复原文的历史乱码记录
- 本仓库检出不含 `data/runs/` 与运行期 SQLite（未提交 Git），乱码记录不在代码库内。
- 需运维方在真实数据环境中：导出疑似乱码记录 → 能重解码的修复、彻底不可恢复的
  按记录隔离/删除并重新质检。若需要，我可基于真实数据样本编写一次性修复/质检脚本。

### ⑦ 第二轮视觉精修与移动端细节打磨
- 属前端打磨，需具体目标（页面 / 组件 / 断点 / 问题清单）方能精准修改；
- 建议在 ② 真实成片验收后，结合真实工作台截图逐项提出，避免无据改动。
