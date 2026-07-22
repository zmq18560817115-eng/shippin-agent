# TikTok 多后端采集与服务器部署

系统不强制使用 TikTok 官方 API。当前采集链路按目标类型选择后端，并在失败时返回真实错误，不伪造成功结果。

## 后端能力

| 后端 | 适用目标 | 服务器要求 | 说明 |
| --- | --- | --- | --- |
| TikTokApi | 账号、话题、关键词、热门 | Playwright Chromium、`TIKTOK_MS_TOKEN`，必要时配置代理 | 非官方开源接口，可能受验证码和页面变更影响 |
| Apify | 关键词 | `APIFY_API_TOKEN` | 托管采集，服务器稳定性通常更高，但会产生费用 |
| yt-dlp | 账号、视频直链下载 | `yt-dlp`，建议 Cookies 文件 | 适合下载和账号公开列表，不负责通用关键词搜索 |
| 人工直链 | 单条视频 | `yt-dlp`，建议 Cookies 文件 | 所有自动发现不可用时的稳定人工入口 |

前端“素材采集”页会显示各后端当前是否可用。运行时状态也可通过 `GET /api/v2/runtime` 查看。

## 推荐的服务器配置

安装依赖：

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-tiktok.txt
python -m playwright install --with-deps chromium
python -m pip install yt-dlp
```

配置服务器环境变量：

```dotenv
TIKTOK_MS_TOKEN=服务账号的msToken
TIKTOK_BROWSER=chromium
TIKTOK_HEADLESS=true
TIKTOK_TIMEOUT_MS=45000
TIKTOK_WORKER_TIMEOUT_SEC=75
TIKTOK_PROXY=

# 推荐：从专用服务账号导出的 Netscape cookies.txt 文件。
TIKTOK_COOKIES_FILE=/srv/video-agent-factory/secrets/tiktok-cookies.txt

# 可选：关键词托管采集。
APIFY_API_TOKEN=
```

TikTokApi 采集在独立子进程中运行，超过 `TIKTOK_WORKER_TIMEOUT_SEC` 会被终止并返回明确错误，不会拖死 API 主进程。当前 TikTokApi 包的“关键词”路径实质上按话题标签发现；系统会自动用产品别名和中英文品类词扩展查询，再进行相关度与热度排序。严格的自然语言关键词检索建议使用 Apify。无字幕视频下载后若要自动转写，还需配置独立的 `VOLCENGINE_ASR_API_KEY`，或旧版 `VOLCENGINE_ASR_APP_KEY` 与 `VOLCENGINE_ASR_ACCESS_KEY`。

`TIKTOK_COOKIES_FILE` 现在同时供 TikTokApi 发现和 yt-dlp 下载使用，建议导出专用服务账号的 Netscape 格式 Cookie 文件。生产入库默认要求 `VAF_TIKTOK_MIN_RELEVANCE=0.50`；当供应商提供播放量时还要求 `VAF_TIKTOK_MIN_PLAYS=5000`。低于门槛的候选会保留筛除原因，但不会下载。

Cookies 文件只放在服务器密钥目录，权限建议为 `600`，禁止提交 Git、放入前端或写入日志。

## 为什么本地可用而服务器失败

本地浏览器通常已经具备登录会话、地区 Cookie 和正常浏览行为；服务器是全新的无头环境，出口 IP 也更容易触发风控。常见原因包括：

- 没有 `msToken` 或 Cookies 文件。
- Playwright 浏览器未安装。
- 数据中心 IP 被限流或要求验证码。
- 服务器地区无法正常访问 TikTok。
- TikTok 页面结构更新，开源适配器暂未同步。

因此“服务器要求官方 API”通常不是代码硬限制，而是非官方后端没有完成会话和网络配置。

## 生产建议

关键词发现建议同时配置 TikTokApi 和 Apify；账号和直链下载保留 yt-dlp；前端始终保留人工直链入口。任何非官方采集方式都无法承诺永久不受 TikTok 反爬策略影响，因此应通过运行状态、失败告警和多后端降级保证业务可恢复，而不是承诺单一爬虫永远有效。
