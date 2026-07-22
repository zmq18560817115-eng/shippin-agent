from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

from tools.collect.tiktok_api_adapter import _load_netscape_cookies


async def _discover(request: dict) -> list[dict]:
    from playwright.async_api import async_playwright

    target = str(request.get("target") or "").strip().lstrip("#")
    limit = max(1, min(int(request.get("limit") or 12), 100))
    wait_ms = max(1000, min(int(request.get("wait_ms") or 12000), 30000))
    headless = str(request.get("headless") or "true").strip().casefold() not in {"0", "false", "no", "off"}
    browser_name = str(request.get("browser") or "chromium").strip().casefold()
    if browser_name not in {"chromium", "firefox", "webkit"}:
        browser_name = "chromium"
    cookies = _load_netscape_cookies(str(request.get("cookies_file") or ""))
    playwright_cookies = [
        {"name": name, "value": value, "domain": ".tiktok.com", "path": "/", "secure": True, "sameSite": "None"}
        for name, value in cookies.items()
    ]
    async with async_playwright() as playwright:
        browser_type = getattr(playwright, browser_name)
        launch_args = ["--disable-blink-features=AutomationControlled"] if browser_name == "chromium" else []
        browser = await browser_type.launch(headless=headless, args=launch_args)
        try:
            context = await browser.new_context(
                locale="en-US",
                timezone_id="America/Los_Angeles",
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            await context.add_cookies(playwright_cookies)
            page = await context.new_page()
            await page.goto(
                "https://www.tiktok.com/search?q=" + quote(target),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(wait_ms)
            for _ in range(5):
                count = await page.locator('a[href*="/video/"]').count()
                if count >= max(limit, 12):
                    break
                await page.mouse.wheel(0, 1800)
                await page.wait_for_timeout(1500)
            raw_items = await page.locator('a[href*="/video/"]').evaluate_all(
                r"""(els, target) => {
                    const seen = new Set();
                    const words = target.toLowerCase().split(/\s+/).filter(word => word.length > 1);
                    const pickText = (a) => {
                        const candidates = [];
                        const add = (value) => {
                            const text = (value || '').replace(/\s+/g, ' ').trim();
                            if (text.length >= 5 && text.length <= 1600) candidates.push(text);
                        };
                        add(a.getAttribute('aria-label'));
                        add(a.getAttribute('title'));
                        add(a.innerText);
                        let node = a;
                        for (let i = 0; i < 9 && node; i += 1, node = node.parentElement) add(node.innerText);
                        const scored = candidates.map(text => {
                            const lower = text.toLowerCase();
                            const matches = words.filter(word => lower.includes(word)).length;
                            const generic = lower.includes('tiktok shop is now available on web') ? 1 : 0;
                            return {text, score: matches * 100 - generic * 500 - text.length / 200};
                        });
                        scored.sort((left, right) => right.score - left.score);
                        return scored[0]?.text || '';
                    };
                    return els.map(a => {
                        const url = a.href.split('?')[0];
                        if (seen.has(url)) return null;
                        seen.add(url);
                        return {
                            url,
                            text: pickText(a).slice(0, 1200),
                            cover: a.querySelector('img')?.src || ''
                        };
                    }).filter(Boolean);
                }""",
                target,
            )
        finally:
            await browser.close()
    items: list[dict] = []
    for raw in raw_items:
        url = str(raw.get("url") or "").strip()
        match = re.search(r"tiktok\.com/@([^/]+)/video/(\d+)", url)
        if not match:
            continue
        text = str(raw.get("text") or "").strip()
        items.append(
            {
                "url": url,
                "title": text.splitlines()[0][:500] if text else "",
                "caption": text,
                "author_name": match.group(1),
                "author_url": f"https://www.tiktok.com/@{match.group(1)}",
                "cover_url": str(raw.get("cover") or ""),
                "hashtags": re.findall(r"#([\w\u4e00-\u9fff]+)", text),
                "play_count": 0,
            }
        )
        if len(items) >= limit:
            break
    return items


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        items = asyncio.run(_discover(request))
        print(json.dumps({"ok": True, "items": items}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
