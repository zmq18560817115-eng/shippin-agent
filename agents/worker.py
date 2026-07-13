from __future__ import annotations

import argparse
import os
import signal
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from agents.base import run_task
from orchestrator import queue


STOP_REQUESTED = threading.Event()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    db_path = Path(args.db_path) if args.db_path else None
    queue.init_db(db_path=db_path)
    _load_handlers()
    _install_signal_handlers()

    worker_id = args.worker_id or f"{os.uname().nodename if hasattr(os, 'uname') else 'worker'}-{uuid.uuid4().hex[:8]}"
    agents = tuple(args.agents.split(",")) if args.agents else None

    while not STOP_REQUESTED.is_set():
        recovered = queue.recover_expired_leases(db_path=db_path)
        if recovered:
            time.sleep(0)

        task = queue.claim_task(
            worker_id,
            agents=agents,
            lease_seconds=args.lease_seconds,
            db_path=db_path,
        )
        if task is None:
            if args.once:
                return
            STOP_REQUESTED.wait(args.poll_interval)
            continue

        _run_claimed_task(
            task,
            worker_id=worker_id,
            lease_seconds=args.lease_seconds,
            db_path=db_path,
        )
        if args.once:
            return


def _run_claimed_task(
    task: queue.Task,
    *,
    worker_id: str,
    lease_seconds: int,
    db_path: Path | None,
) -> None:
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(task.id, worker_id, lease_seconds, db_path, heartbeat_stop),
        daemon=True,
    )
    heartbeat.start()
    try:
        result = run_task(_task_to_mapping(task))
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=1)

    if result.status == "succeeded":
        queue.complete_task(task.id, worker_id, result.result, db_path=db_path)
    elif result.status == "blocked":
        queue.mark_task_status(
            task.id,
            "blocked",
            worker_id=worker_id,
            error=result.error,
            db_path=db_path,
        )
    else:
        queue.fail_task(
            task.id,
            worker_id,
            result.error or {"category": "unknown", "message": "task failed"},
            retryable=result.retryable,
            db_path=db_path,
        )


def _heartbeat_loop(
    task_id: int,
    worker_id: str,
    lease_seconds: int,
    db_path: Path | None,
    stop_event: threading.Event,
) -> None:
    interval = max(0.2, min(5.0, lease_seconds / 3))
    while not stop_event.wait(interval):
        queue.heartbeat_task(
            task_id,
            worker_id,
            lease_seconds=lease_seconds,
            db_path=db_path,
        )


def _task_to_mapping(task: queue.Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "stage": task.stage,
        "agent": task.agent,
        "task_type": task.task_type,
        "status": task.status,
        "attempt": task.attempt,
        "max_retries": task.max_retries,
        "payload_json": task.payload_json,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="video-agent-factory worker")
    parser.add_argument("--db-path", default=os.environ.get("VAF_DB_PATH"))
    parser.add_argument("--worker-id", default=os.environ.get("VAF_WORKER_ID"))
    parser.add_argument("--lease-seconds", type=int, default=queue.resolve_lease_seconds())
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.environ.get("VAF_WORKER_POLL_INTERVAL", "1.0")),
    )
    parser.add_argument("--agents", help="comma-separated agent allowlist")
    parser.add_argument("--once", action="store_true", help="claim at most one task")
    return parser.parse_args(argv)


def _install_signal_handlers() -> None:
    def request_stop(signum: int, frame: object) -> None:
        STOP_REQUESTED.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(signum, request_stop)
        except ValueError:
            pass


def _load_handlers() -> None:
    # Import side effects populate agents.base.HANDLERS.
    from agents.handlers import analysis, asset, collector, media, review, script, storyboard

    _ = (analysis, asset, collector, media, review, script, storyboard)


if __name__ == "__main__":
    main()
