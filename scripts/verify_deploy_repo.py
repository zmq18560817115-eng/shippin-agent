from __future__ import annotations

import plistlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_PATHS = [
    "orchestrator/api.py",
    "orchestrator/schema.sql",
    "agents/worker.py",
    "agents/handlers/collector.py",
    "tools/collect/manual_import.py",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
    "deploy/macos/com.vaf.orchestrator.plist",
    "deploy/macos/com.vaf.worker.plist",
    "deploy/macos/deploy.sh",
    "pipeline_defs/viral-imitate.yaml",
    "data/01_素材库",
    "data/03_产出库",
    "data/04_成稿库",
    "data/05_反馈库",
]


def verify(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_PATHS:
        path = root / relative
        if not path.exists():
            errors.append(f"missing: {relative}")

    for plist_name in ("com.vaf.orchestrator.plist", "com.vaf.worker.plist"):
        path = root / "deploy" / "macos" / plist_name
        if not path.exists():
            continue
        try:
            payload = plistlib.loads(path.read_bytes())
        except Exception as exc:
            errors.append(f"invalid plist {plist_name}: {exc}")
            continue
        if payload.get("KeepAlive") is not True:
            errors.append(f"{plist_name}: KeepAlive must be true")
        if payload.get("RunAtLoad") is not True:
            errors.append(f"{plist_name}: RunAtLoad must be true")
        if not payload.get("ProgramArguments"):
            errors.append(f"{plist_name}: ProgramArguments is required")
        if "__VAF_ROOT__" not in str(payload):
            errors.append(f"{plist_name}: template token __VAF_ROOT__ is required")

    deploy_sh = root / "deploy" / "macos" / "deploy.sh"
    if deploy_sh.exists():
        text = deploy_sh.read_text(encoding="utf-8")
        for marker in ("launchctl", "healthz", "pmset", ".venv"):
            if marker not in text:
                errors.append(f"deploy.sh missing marker: {marker}")
    return errors


def main() -> int:
    errors = verify()
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print("deploy repo verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
