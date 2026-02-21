#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

DATA_DIR = Path(__file__).parent.parent / "data"
FETCH_SCRIPT = Path(__file__).parent.parent / "fetch_data.py"

app = FastAPI(title="Financial Data API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_update_lock = threading.Lock()
_update_status: dict = {"running": False, "last_run": None, "error": None}


@app.get("/api/tickers")
def list_tickers():
    return sorted(f.stem for f in DATA_DIR.glob("*.records"))


@app.get("/api/data/{ticker}")
def get_data(
    ticker: str,
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    filepath = DATA_DIR / f"{ticker.upper()}.records"
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"{ticker} not found")

    bars: list[dict] = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sep = line.index(": ")
            date_str = line[:sep]
            if start and date_str < start:
                continue
            if end and date_str > end:
                continue
            for bar in json.loads(line[sep + 2:]):
                bars.append({"date": date_str, **bar})

    return {"ticker": ticker.upper(), "bars": bars}


@app.post("/api/update")
def trigger_update(body: dict = {}):
    tickers: list[str] = body.get("tickers", [])

    with _update_lock:
        if _update_status["running"]:
            return {"status": "already_running"}
        _update_status["running"] = True
        _update_status["error"] = None

    def run():
        try:
            cmd = ["python3", str(FETCH_SCRIPT)]
            if tickers:
                cmd += [t.upper() for t in tickers]
            subprocess.run(cmd, cwd=str(FETCH_SCRIPT.parent), capture_output=True, text=True)
            _update_status["last_run"] = datetime.now().isoformat()
        except Exception as e:
            _update_status["error"] = str(e)
        finally:
            _update_status["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return {"status": "started"}


@app.get("/api/update/status")
def update_status():
    return _update_status
