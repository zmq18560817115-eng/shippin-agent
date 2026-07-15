# TikTokApi 自建采集接入

本项目把 `davidteather/TikTok-Api` 作为可选采集后端，不复制其源码。它负责发现公开账号、话题和热门视频；现有 `yt-dlp` 仍负责视频下载，Research Agent 继续负责转写与分析。

## 1. 安装依赖

在项目根目录运行：

```powershell
python -m pip install -r requirements-tiktok.txt
python -m playwright install chromium
```

## 2. 配置会话

1. 用浏览器正常访问 TikTok。
2. 打开开发者工具，在 Application/Storage 的 Cookies 中找到 `msToken`。
3. 在项目根目录的 `.env.local` 中填写：

```dotenv
TIKTOK_MS_TOKEN=你的msToken
TIKTOK_BROWSER=chromium
TIKTOK_HEADLESS=true
TIKTOK_TIMEOUT_MS=45000
```

`msToken` 属于敏感会话信息，不要提交 Git、不要粘贴到前端。若当前网络被 TikTok 限流，可选配置 `TIKTOK_PROXY=http://host:port`。
若返回机器人识别错误，可设置 `TIKTOK_HEADLESS=false`，让采集任务使用短暂出现的可见浏览器窗口。

## 3. 支持范围

- `account`：账号主页、`@用户名` 或用户名，使用 TikTokApi。
- `hashtag`：话题名或 `#话题`，使用 TikTokApi。
- `trending`：热门公开视频，使用 TikTokApi。
- `keyword`：`auto` 模式优先走 Apify 精确关键词；未配置 Apify 时把关键词按话题采集。

TikTokApi 是非官方公开数据接口，可能受地区、验证码、风控和 TikTok 页面变更影响。系统会返回明确错误，不会静默伪造成功结果。
