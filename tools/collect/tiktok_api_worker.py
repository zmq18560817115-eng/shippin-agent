from __future__ import annotations

import json
import sys

from tools.collect.tiktok_api_adapter import discover_direct


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        env = {
            "TIKTOK_BROWSER": str(request.get("browser") or "chromium"),
            "TIKTOK_PROXY": str(request.get("proxy") or ""),
            "TIKTOK_TIMEOUT_MS": str(request.get("timeout_ms") or "45000"),
            "TIKTOK_HEADLESS": str(request.get("headless") or "true"),
            "TIKTOK_COOKIES_FILE": str(request.get("cookies_file") or ""),
        }
        items = discover_direct(
            target_type=str(request.get("target_type") or "keyword"),
            target=str(request.get("target") or ""),
            limit=max(1, min(int(request.get("limit") or 6), 100)),
            env=env,
            token=str(request.get("token") or ""),
        )
        print(json.dumps({"ok": True, "items": items}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
