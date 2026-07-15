"""Load local development credentials without placing them in source control."""

from __future__ import annotations

import os
from pathlib import Path

from libshared.paths import ROOT


def load_local_env(path: Path | None = None) -> None:
    """Populate missing process variables from the ignored ``.env.local`` file.

    Process-level values always take precedence so production deployments and
    tests remain explicit. The deliberately small parser supports the usual
    ``KEY=value`` form without introducing another runtime dependency.
    """

    env_path = path or ROOT / ".env.local"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
