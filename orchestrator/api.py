from __future__ import annotations

from fastapi import FastAPI


app = FastAPI(title="video-agent-factory", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
