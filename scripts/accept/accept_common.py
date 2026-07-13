from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8790


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen[str]

    @property
    def pid(self) -> int:
        return self.process.pid

    def terminate(self, timeout_s: float = 5.0) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self.kill()

    def kill(self) -> None:
        if self.process.poll() is not None:
            return
        if os.name == "nt":
            self.process.kill()
        else:
            os.kill(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=5)


def _merged_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    if extra:
        env.update(extra)
    return env


def start_process(
    name: str,
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path = ROOT,
) -> ManagedProcess:
    process = subprocess.Popen(
        list(args),
        cwd=str(cwd),
        env=_merged_env(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return ManagedProcess(name=name, process=process)


def start_orchestrator(*, port: int = DEFAULT_PORT) -> ManagedProcess:
    return start_process(
        "orchestrator",
        [
            sys.executable,
            "-m",
            "uvicorn",
            "orchestrator.api:app",
            "--host",
            DEFAULT_HOST,
            "--port",
            str(port),
        ],
    )


def start_worker() -> ManagedProcess:
    return start_process("worker", [sys.executable, "-m", "agents.worker"])


def wait_http_ready(url: str, *, timeout_s: float = 10.0) -> None:
    import httpx

    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code < 500:
                return
        except Exception as exc:  # pragma: no cover - only used by accept scripts
            last_error = exc
        time.sleep(0.2)
    raise TimeoutError(f"{url} did not become ready") from last_error


@contextmanager
def managed_services(*, port: int = DEFAULT_PORT) -> Iterator[tuple[ManagedProcess, ManagedProcess]]:
    orchestrator = start_orchestrator(port=port)
    worker = start_worker()
    try:
        wait_http_ready(f"http://{DEFAULT_HOST}:{port}/healthz")
        yield orchestrator, worker
    finally:
        worker.terminate()
        orchestrator.terminate()
