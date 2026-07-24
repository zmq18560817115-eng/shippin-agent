# 视频内容工厂

面向海外产品短视频团队的中文 Agent 工作台。系统把产品素材、TikTok 参考内容、内容研究、策略、脚本、分镜、镜头生成、人工验收和 720P 交付组织为一条可追踪的生产链路，同时允许各 Agent 作为快速工具独立运行。

> 当前定位：内部试运行系统。演练模式可完成全链路回归；真实模式需要有效的模型密钥、TikTok 会话、视频依赖和人工质量验收。

## 核心能力

- **视频项目**：项目概览、策略、脚本、分镜、镜头制作、成片验收和交付归档。
- **独立 Agent**：研究分析、策略、脚本生成、脚本拆解、分镜生成、单镜视频、审核等能力可独立调用。
- **素材中心**：产品素材、TikTok 参考素材、后台采集任务、转写与镜头拆解。
- **人工闸门**：脚本确认、关键帧确认、Take 选择和成片视觉终审。
- **交付约束**：竖屏 `720x1280`、30fps、H.264/AAC、约 30 秒、可播放且带抽帧证据。
- **管理后台**：成员与注册审核、项目和任务统计、模型与采集后端状态、部署就绪度。

## 工作流

```text
产品与参考素材
  -> 研究分析
  -> 内容策略
  -> 脚本生成与拆解
  -> 脚本人工确认
  -> 分镜与关键帧
  -> 关键帧人工确认
  -> 多 Take 生成与选择
  -> 30 秒合成
  -> 自动质检与人工终审
  -> 交付归档
```

演练模式不调用外部模型，用于培训和回归；真实模式调用豆包与 Seedance，可能产生费用。两种模式使用相同的人工闸门和交付检查。

## 5 分钟启动

### 1. 安装

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-tiktok.txt
playwright install chromium
```

需要本地离线 ASR 时再安装：

```powershell
pip install -r requirements-local-asr.txt
```

### 2. 配置

```powershell
Copy-Item .env.example .env.local
```

演练模式最小配置：

```dotenv
VAF_AUTH_ENABLED=false
VAF_HOST=127.0.0.1
VAF_PORT=8790
```

内网部署至少配置：

```dotenv
VAF_AUTH_ENABLED=true
VAF_SESSION_SECRET=至少32位随机字符串
VAF_OPERATOR_USER=operator
VAF_OPERATOR_PASSWORD=强密码
VAF_ADMIN_USER=admin
VAF_ADMIN_PASSWORD=强密码

DOUBAO_API_KEY=
SEEDANCE_API_KEY=
TIKTOK_COOKIES_FILE=/data/secrets/tiktok-cookies.txt
```

真实密钥、Cookies 和密码只放在服务器环境变量或 `.env.local`，禁止提交到 Git。

### 3. 预检和启动

```powershell
python scripts/deployment_preflight.py --env-file .env.local
python -m uvicorn orchestrator.api:app --host 0.0.0.0 --port 8790
```

访问：

- 登录入口：`http://127.0.0.1:8790/`
- 生产工作台：`http://127.0.0.1:8790/workbench`
- 管理后台：`http://127.0.0.1:8790/admin`
- 健康检查：`http://127.0.0.1:8790/healthz`

首次使用请阅读 [新手使用指南](docs/新手使用指南.md)。

## TikTok 采集

自动采集优先使用后台任务。关键词发现、相关度筛选、下载、封面、字幕或 ASR、转写和结构化拆解均在服务端执行，关闭浏览器不会中断任务。

推荐配置：

```dotenv
TIKTOK_COOKIES_FILE=/data/secrets/tiktok-cookies.txt
TIKTOK_BROWSER=chromium
TIKTOK_HEADLESS=true
VAF_TIKTOK_MIN_RELEVANCE=0.50
VAF_TIKTOK_MIN_PLAYS=5000
VAF_TIKTOK_REQUIRE_PLAY_METRIC=true
VAF_LOCAL_ASR_ENABLED=true
VAF_LOCAL_ASR_MODEL=base
```

管理后台可以安全上传 Netscape 格式的 TikTok Cookies。上传后必须运行“检测采集”，因为“文件存在”不等于 TikTok 会话仍然有效。

后台终态任务会自动清理，但已入库素材不会删除：

```dotenv
VAF_COLLECTION_CLEANUP_ENABLED=true
VAF_COLLECTION_CLEANUP_INTERVAL_SECONDS=3600
VAF_COLLECTION_SUCCEEDED_RETENTION_DAYS=7
VAF_COLLECTION_FAILED_RETENTION_DAYS=14
```

TikTok 可用性受地区、账号状态、Cookies 有效期和平台策略影响。系统保留 TikTokApi、浏览器搜索、Apify 和人工直链等多后端降级路径，但不会把缓存结果冒充实时发现。

## 真实模型与质量边界

文本模型负责研究、策略、脚本、分镜和审核；Seedance 负责单镜视频。模型输出不能直接视为合格成片，必须经过以下检查：

1. 产品外观与批准素材一致，不虚构品牌、Logo 或文字。
2. 温标只允许 `98°F`，禁止 `98°C`。
3. 液体使用方向正确，产品与独立奶瓶保持清晰关系。
4. 人物、服装、场景、光线与产品外观跨镜连续。
5. 每个镜头选择一个可播放且通过人工检查的 Take。
6. 成片严格为 `720x1280`，有音轨、约 30 秒并生成至少 3 张复核抽帧。

真实模式上线前至少跑一条完整样片并保存运行报告、最终视频和人工终审记录。

## 数据与持久化

建议将以下目录挂载到持久卷：

- `data/`：SQLite、素材库、运行产物与交付文件。
- `secrets/`：TikTok Cookies 等本地秘密文件。
- 本地 ASR 模型缓存目录。

仓库只提交示例产品素材与反馈样本；`data/runs/`、SQLite 数据库、真实下载素材、模型输出和密钥不提交 Git。

## 验收

```powershell
python -m pytest tests scripts/accept -q
node --check web/app.js
node --check web/admin.js
node --check web/login.js
python scripts/accept/run_a8_10videos.py
```

CI 会在 push 和 pull request 时运行 Python 测试及三个前端脚本的语法检查。`scripts/accept/report_10videos.md` 是演练模式批量验收报告，不等同于真实模型生产验收。

### P0/P1 生产闭环

- Seedance 付费生成前会校验产品身份、温标显示、连续性和动作方向契约；第 4 镜还必须声明圆形出液口、独立奶瓶、奶瓶结构证据及禁止反向倒液。
- 每个真实 Take 自动抽帧。OCR 检查 `98°F`/禁用 `98°C`，低流量豆包视觉检查产品结构、目标容器和倒液方向；视觉能力不可用时明确降级为人工复核，不会伪装通过。
- 非温标镜头强制屏幕熄灭、不可读或避开画面。所有自动检查都不能替代逐镜人工质检和成片人工终审。
- TikTok 后台任务支持定时运行、租约心跳、失败重试、进程重启续跑、低相关/低热度过滤、缺视频/封面/转写隔离、终态任务定时清理及失败原因分类统计。
- 策略、脚本与分镜均附带结构化质量评分；分镜必须逐段保留脚本角色、时间、场景、动作和剧情推进。
- 独立 Agent 产物可以下载、保存，并通过“用此产物创建生产项目”回灌正式流水线。
- 管理后台对预算使用达到 80% 的项目和采集失败记录给出告警。真实项目默认使用 `enforce` 预算模式。

真实出片验收不得只看接口成功：必须保存逐镜 Take 质检、抽帧报告、30 秒 `720x1280` 成片、最终人工终审和成本记录。

## 常见问题

### 后台显示 TikTok Cookies 待配置

1. 在 Chrome/Edge 登录 `tiktok.com`，使用 Cookie 导出扩展导出 **Netscape 格式 `.txt`** 文件。
2. 使用管理员账号打开 `/admin`，在“服务状态”右上角点击“更新 Cookies”并选择该文件。
3. 上传成功后点击“检测采集”。系统会自动优先检测浏览器搜索；浏览器链路尚未就绪时自动检测 TikTokApi 备用采集。
4. 页面只显示文件是否可读和探针状态，不会回传 Cookie 内容。Cookie 过期后重复上述操作即可。

内网服务器不能读取开发电脑的 Windows 路径。后台上传会把文件写入服务器 `data/secrets/tiktok-cookies.txt` 并立即供当前进程使用，无需手改 `.env.local`。服务器仍需在**启动服务的同一 Python 环境**执行一次：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

如果使用 Linux 且缺少 Chromium 系统依赖，执行 `python -m playwright install --with-deps chromium`。重启服务后，管理后台中的“TikTok 浏览器搜索”“视频下载器”“人工链接”应不再显示依赖缺失。

### 真实运行创建失败

先检查管理后台的豆包、Seedance、FFmpeg、Playwright、视频下载器、Cookies、ASR 和存储状态。缺少真实模型密钥时系统应拒绝创建真实项目，而不是在下游静默失败。

### 项目停在等待人工

这是预期行为。依次完成脚本确认、关键帧确认、每镜 Take 选择和成片人工终审，流程才会继续。

### 采集任务越来越多

终态任务默认定时清理。清理只删除队列记录及临时候选，不删除已入库素材。保留周期可通过 `VAF_COLLECTION_*_RETENTION_DAYS` 调整。

## 目录

- `orchestrator/`：FastAPI、队列、流程引擎、闸门、鉴权和质量检查。
- `tools/`：采集、LLM、ASR、视频生成、FFmpeg 和产品素材工具。
- `pipeline_defs/`：工作流定义。
- `schemas/artifacts/`：结构化产物 Schema。
- `web/`：登录、生产工作台和管理后台。
- `scripts/accept/`：端到端验收与批量报告。
- `docs/`：部署、模型验收、能力审计和使用文档。

## 延伸文档

- [新手使用指南](docs/新手使用指南.md)
- [内网部署与数据持久化](docs/内网部署与数据持久化.md)
- [TikTokApi 接入说明](docs/TikTokApi接入说明.md)
- [真实模型验收记录](docs/real-model-acceptance-2026-07-20.md)
- [Agent 能力地图审计](docs/Agent能力地图审计-2026-07-14.md)
