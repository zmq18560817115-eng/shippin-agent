from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from orchestrator import queue


def _wait_until(predicate: Callable[[], bool], timeout_s: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise TimeoutError("condition was not met before timeout")


def _start_worker(db_path: Path, *, lease_seconds: int = 1) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["VAF_ENABLE_DUMMY_TASKS"] = "1"
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agents.worker",
            "--db-path",
            str(db_path),
            "--lease-seconds",
            str(lease_seconds),
            "--poll-interval",
            "0.05",
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop_worker(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.kill()
    process.wait(timeout=5)


def test_a1_killed_worker_task_is_recovered_and_reclaimed(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(
        project_id="ref-a1",
        stage="analysis",
        agent="analysis",
        task_type="dummy",
        payload={"dummy": "sleep_then_success", "sleep_s": 30, "success_after_attempt": 2},
        max_retries=2,
        db_path=db_path,
    )

    first_worker = _start_worker(db_path, lease_seconds=1)
    try:
        _wait_until(lambda: queue.get_task(task_id, db_path=db_path).status == "running")
        first_attempt = queue.get_task(task_id, db_path=db_path)
        assert first_attempt.attempt == 1
        _stop_worker(first_worker)

        time.sleep(1.2)
        recovered = queue.recover_expired_leases(db_path=db_path)
        assert recovered == 1
        assert queue.get_task(task_id, db_path=db_path).status == "queued"

        second_worker = _start_worker(db_path, lease_seconds=1)
        try:
            _wait_until(lambda: queue.get_task(task_id, db_path=db_path).status == "succeeded")
            completed = queue.get_task(task_id, db_path=db_path)
            assert completed.attempt == 2
            assert completed.result_json["dummy"] == "ok"
        finally:
            _stop_worker(second_worker)
    finally:
        _stop_worker(first_worker)


def test_a1_retryable_failure_stops_at_max_retries(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(
        project_id="ref-a1",
        stage="script",
        agent="script",
        task_type="dummy",
        payload={"dummy": "fail_retryable"},
        max_retries=2,
        db_path=db_path,
    )

    worker = _start_worker(db_path, lease_seconds=1)
    try:
        _wait_until(lambda: queue.get_task(task_id, db_path=db_path).status == "failed")
        failed = queue.get_task(task_id, db_path=db_path)
        assert failed.attempt == 2
        assert failed.error_json["category"] == "transient"
    finally:
        _stop_worker(worker)


def test_a1_media_tasks_are_claimed_serially(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    first_media = queue.enqueue_task(
        project_id="ref-a1",
        stage="production",
        agent="media",
        task_type="shot_gen",
        payload={"shot_index": 1},
        db_path=db_path,
    )
    second_media = queue.enqueue_task(
        project_id="ref-a1",
        stage="production",
        agent="media",
        task_type="shot_gen",
        payload={"shot_index": 2},
        db_path=db_path,
    )
    analysis_task = queue.enqueue_task(
        project_id="ref-a1",
        stage="analysis",
        agent="analysis",
        task_type="dummy",
        payload={"dummy": "success"},
        db_path=db_path,
    )

    claimed_media = queue.claim_task("worker-1", agents=["media"], db_path=db_path)
    assert claimed_media is not None
    assert claimed_media.id == first_media
    assert queue.claim_task("worker-2", agents=["media"], db_path=db_path) is None

    claimed_analysis = queue.claim_task("worker-2", agents=["analysis"], db_path=db_path)
    assert claimed_analysis is not None
    assert claimed_analysis.id == analysis_task

    queue.complete_task(first_media, "worker-1", {"ok": True}, db_path=db_path)
    claimed_second_media = queue.claim_task("worker-2", agents=["media"], db_path=db_path)
    assert claimed_second_media is not None
    assert claimed_second_media.id == second_media
