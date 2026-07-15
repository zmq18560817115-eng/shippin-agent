from __future__ import annotations

import os

from libshared.local_env import load_local_env


def test_load_local_env_populates_missing_values_without_overriding(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text("TOKEN=from-file\nQUOTED='safe value'\n# ignored\n", encoding="utf-8")
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.setenv("QUOTED", "from-process")

    load_local_env(env_file)

    assert os.environ["TOKEN"] == "from-file"
    assert os.environ["QUOTED"] == "from-process"
