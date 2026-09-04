"""
demo/webdash/app.py — Phase 4 WOW #2: web dashboard server.

FastAPI + WebSocket server that:
  - Pushes live pipeline telemetry to connected clients at 4 Hz
  - Exposes /mode/{enhance|bypass} so a judge can toggle from a phone
  - Serves a single-page HTML client at /

Mode-switch path:  pipeline._mode = mode
  This is the same atomic CPython assignment used by demo/dashboard.py:114-116
  (§3.1 of phase4_plan.md).  Both entry points share one implementation so any
  needed engine/filter reset is handled in exactly one place.

Security scope: unauthenticated, LAN-only, demo-scoped.  No secrets served.
Bind: 0.0.0.0:8080 (override via --host / --port or config).

Usage:
    python demo/webdash/app.py --help
    python demo/webdash/app.py --self-test  (no audio hardware needed)
    python demo/webdash/app.py --backup demo/backup_audio/backup_60s.wav  (Phase 5.1)
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import numpy as np
    _NP_OK = True
except ImportError:
    _NP_OK = False

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    _FASTAPI_OK = True
except ImportError:
    _FASTAPI_OK = False

# ---------------------------------------------------------------------------
# Single-page HTML client (embedded — no static directory dependency on Pi)
# ---------------------------------------------------------------------------
_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>PS26052 Live Dashboard</title>
<style>
:root{--bg:#111;--surface:#1e1e1e;--border:#333;--text:#eee;--muted:#888;
  --green:#4caf50;--red:#f44336;--amber:#ff9800;--blue:#2196f3;--accent:#03a9f4;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;
  min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:16px;}
h1{font-size:1.1rem;letter-spacing:.05em;color:var(--muted);margin-bottom:16px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:16px;width:100%;max-width:420px;margin-bottom:12px;}
.row{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.label{color:var(--muted);font-size:.85rem;text-transform:uppercase;letter-spacing:.05em;}
.value{font-size:1.1rem;font-weight:600;}
.mode-badge{display:inline-block;padding:4px 14px;border-radius:20px;font-size:.9rem;
  font-weight:700;text-transform:uppercase;letter-spacing:.1em;}
.enhance{background:var(--green);color:#000;}
.bypass{background:var(--amber);color:#000;}
#toggle-btn{width:100%;padding:14px;border:none;border-radius:10px;font-size:1rem;
  font-weight:700;cursor:pointer;letter-spacing:.05em;margin-top:4px;}
.conf-bar-wrap{flex:1;margin-left:12px;background:var(--border);border-radius:4px;height:8px;}
.conf-bar{height:8px;border-radius:4px;background:var(--accent);transition:width .3s;}
.mos-box{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:4px;}
.mos-cell{text-align:center;padding:8px;background:var(--bg);border-radius:8px;}
.mos-cell .v{font-size:1.3rem;font-weight:700;}
.mos-cell .k{font-size:.75rem;color:var(--muted);}
.warn{color:var(--red);}
.ok{color:var(--green);}
.dim{color:var(--muted);}
#status{font-size:.75rem;color:var(--muted);text-align:center;margin-top:8px;}
</style>
</head>
<body>
<h1>PS26052 · ANC Live Dashboard</h1>

<div class="card">
  <div class="row">
    <span class="label">Mode</span>
    <span id="mode-badge" class="mode-badge enhance">ENHANCE</span>
  </div>
  <button id="toggle-btn" onclick="toggleMode()">Switch to BYPASS</button>
</div>

<div class="card">
  <div class="row"><span class="label">Noise Category</span>
    <span id="cat" class="value">—</span></div>
  <div class="row"><span class="label">Confidence</span>
    <div class="conf-bar-wrap"><div id="conf-bar" class="conf-bar" style="width:0%"></div></div>
    <span id="conf-pct" class="value" style="min-width:40px;text-align:right">—</span>
  </div>
</div>

<div class="card">
  <div class="row"><span class="label">DNSMOS P.835</span>
    <span id="mos-status" class="dim">measuring…</span></div>
  <div class="mos-box">
    <div class="mos-cell"><div id="mos-sig" class="v dim">—</div><div class="k">SIG</div></div>
    <div class="mos-cell"><div id="mos-ovr" class="v dim">—</div><div class="k">OVR</div></div>
    <div class="mos-cell"><div id="mos-bak" class="v dim">—</div><div class="k">BAK</div></div>
  </div>
</div>

<div class="card">
  <div class="row"><span class="label">RTF</span><span id="rtf" class="value">—</span></div>
  <div class="row"><span class="label">Chunk latency</span><span id="lat" class="value">—</span></div>
  <div class="row"><span class="label">In level</span><span id="in-db" class="value">—</span></div>
  <div class="row"><span class="label">Out level</span><span id="out-db" class="value">—</span></div>
</div>

<div id="status">Connecting…</div>

<script>
let currentMode = "enhance";
let ws;

function connect() {
  ws = new WebSocket((location.protocol==="https:"?"wss://":"ws://") + location.host + "/ws");
  ws.onopen = () => document.getElementById("status").textContent = "Connected";
  ws.onclose = () => { document.getElementById("status").textContent = "Reconnecting…"; setTimeout(connect, 2000); };
  ws.onerror = () => ws.close();
  ws.onmessage = (e) => {
    const d = JSON.parse(e.data);
    currentMode = d.mode || "enhance";
    const badge = document.getElementById("mode-badge");
    badge.textContent = currentMode.toUpperCase();
    badge.className = "mode-badge " + currentMode;
    document.getElementById("toggle-btn").textContent =
      "Switch to " + (currentMode === "enhance" ? "BYPASS" : "ENHANCE");
    document.getElementById("toggle-btn").style.background =
      currentMode === "enhance" ? "#f44336" : "#4caf50";
    document.getElementById("toggle-btn").style.color = "#fff";

    const cat = d.noise_category || "UNKNOWN";
    document.getElementById("cat").textContent = cat;
    const conf = (d.noise_confidence || 0) * 100;
    document.getElementById("conf-bar").style.width = conf.toFixed(0) + "%";
    document.getElementById("conf-pct").textContent = conf.toFixed(0) + "%";

    if (d.mos_valid) {
      document.getElementById("mos-status").textContent = "";
      ["sig","ovr","bak"].forEach(k => {
        const el = document.getElementById("mos-"+k);
        const v = d["mos_"+k];
        el.textContent = v != null ? v.toFixed(2) : "—";
        el.className = "v " + (v != null && v < 2.5 ? "warn" : "ok");
      });
    } else {
      document.getElementById("mos-status").textContent = "measuring…";
      ["sig","ovr","bak"].forEach(k => {
        document.getElementById("mos-"+k).textContent = "—";
        document.getElementById("mos-"+k).className = "v dim";
      });
    }

    document.getElementById("rtf").textContent = d.rtf != null ? d.rtf.toFixed(3) : "—";
    document.getElementById("lat").textContent = d.latency_ms != null ? d.latency_ms.toFixed(1) + " ms" : "—";
    document.getElementById("in-db").textContent = d.in_level_db != null ? d.in_level_db.toFixed(1) + " dBFS" : "—";
    document.getElementById("out-db").textContent = d.out_level_db != null ? d.out_level_db.toFixed(1) + " dBFS" : "—";
  };
}

function toggleMode() {
  const next = currentMode === "enhance" ? "bypass" : "enhance";
  fetch("/mode/" + next).catch(() => {});
}

connect();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Telemetry builder
# ---------------------------------------------------------------------------
def _build_telemetry(pipeline, telemetry=None) -> dict:
    """Build JSON-safe telemetry dict from pipeline display hooks + Phase 4 telemetry."""
    latencies = list(getattr(pipeline, "_chunk_latencies", None) or [])
    chunk_sec = float(getattr(pipeline, "_chunk_sec", 0.1) or 0.1)
    rtf = 0.0
    lat_ms = 0.0
    if latencies:
        med = sorted(latencies)[len(latencies) // 2]
        rtf = med / chunk_sec
        lat_ms = med * 1000.0

    def _rms_db(arr):
        if arr is None or not _NP_OK:
            return -96.0
        arr = np.asarray(arr, dtype=np.float32)
        rms = float(np.sqrt(np.mean(arr ** 2))) if arr.size > 0 else 0.0
        return 20.0 * math.log10(max(rms, 1e-10))

    payload: dict = {
        "ts": time.time(),
        "mode": getattr(pipeline, "_mode", "enhance"),
        "rtf": round(rtf, 3),
        "latency_ms": round(lat_ms, 1),
        "in_level_db": round(_rms_db(getattr(pipeline, "last_in_chunk", None)), 1),
        "out_level_db": round(_rms_db(getattr(pipeline, "last_out_chunk", None)), 1),
    }

    if telemetry is not None:
        payload.update(telemetry.snapshot())
    else:
        payload.update({
            "noise_category": "UNKNOWN",
            "noise_confidence": 0.0,
            "impulsive_event_count": 0,
            "mos_sig": None,
            "mos_bak": None,
            "mos_ovr": None,
            "mos_valid": False,
        })
    return payload


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------
def make_app(pipeline, telemetry=None, telemetry_hz: float = 4.0):
    """
    Build and return the FastAPI application.

    Parameters
    ----------
    pipeline   : object with ._mode (str, r/w), .last_in_chunk, .last_out_chunk,
                 ._chunk_latencies (list[float]), ._chunk_sec (float)
    telemetry  : PipelineTelemetry or None — Phase 4 noise/MOS fields
    telemetry_hz : WebSocket push rate in Hz (default 4)
    """
    if not _FASTAPI_OK:
        raise ImportError(
            "fastapi is required for the web dashboard. "
            "Install it: pip install fastapi uvicorn[standard]"
        )

    app = FastAPI(title="PS26052 Live Dashboard", docs_url=None, redoc_url=None)
    _interval = 1.0 / max(telemetry_hz, 0.5)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_INDEX_HTML)

    @app.get("/mode/{mode}")
    async def set_mode(mode: str):
        if mode not in ("enhance", "bypass"):
            return {"error": f"unknown mode {mode!r}", "valid": ["enhance", "bypass"]}
        pipeline._mode = mode  # atomic CPython assignment — same as dashboard.py:114-116
        return {"mode": mode, "ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                payload = _build_telemetry(pipeline, telemetry)
                await websocket.send_text(json.dumps(payload))
                await asyncio.sleep(_interval)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def _run_selftest():
    """Mode A self-test: mock pipeline, no audio hardware required."""
    import threading

    if not _FASTAPI_OK:
        print("[SKIP] fastapi not installed — install fastapi uvicorn[standard]")
        sys.exit(0)  # SKIP, not FAIL

    try:
        from starlette.testclient import TestClient
    except ImportError:
        print("[SKIP] starlette.testclient not available (install httpx)")
        sys.exit(0)

    class _MockPipeline:
        _mode = "enhance"
        last_in_chunk = None
        last_out_chunk = None
        _chunk_latencies = [0.035, 0.036, 0.034]
        _chunk_sec = 0.1

    pipe = _MockPipeline()
    app = make_app(pipe, telemetry=None, telemetry_hz=4.0)
    client = TestClient(app, raise_server_exceptions=True)

    # 1. Index page serves HTML
    r = client.get("/")
    assert r.status_code == 200, f"/ returned {r.status_code}"
    assert "PS26052" in r.text, "index.html missing title"

    # 2. Mode switch: enhance → bypass
    r = client.get("/mode/bypass")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True, f"mode switch returned {data}"
    assert pipe._mode == "bypass", f"_mode not updated: {pipe._mode!r}"

    # 3. Mode switch: bypass → enhance
    r = client.get("/mode/enhance")
    assert r.status_code == 200
    assert pipe._mode == "enhance"

    # 4. Unknown mode returns error (not 5xx)
    r = client.get("/mode/unknown")
    assert r.status_code == 200
    assert "error" in r.json()

    # 5. WebSocket emits valid JSON with required keys
    with client.websocket_connect("/ws") as ws:
        raw = ws.receive_text()
        payload = json.loads(raw)
        for key in ("ts", "mode", "rtf", "latency_ms", "noise_category", "mos_valid"):
            assert key in payload, f"telemetry missing key {key!r}"
        assert payload["mode"] == "enhance"
        assert isinstance(payload["rtf"], float)
        assert payload["mos_valid"] is False

    print("[PASS] demo/webdash/app.py self-test")


def main():
    parser = argparse.ArgumentParser(description="PS26052 web dashboard server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--backup",
        default=None,
        metavar="WAV_PATH",
        help="Phase 5.1: play this WAV file instead of the live microphone "
             "(see demo/backup_playback.py). Real output hardware is still used.",
    )
    args = parser.parse_args()

    if args.self_test:
        _run_selftest()
        return

    # Live mode: import and start the real pipeline
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    from live.pipeline import LivePipeline, _load_config
    cfg = _load_config("config/audio_config.yaml")

    pipeline = LivePipeline(cfg, backup_audio_path=args.backup)
    pipeline.start()

    app = make_app(
        pipeline,
        telemetry=None,   # wire up PipelineTelemetry here when classifier/DNSMOS enabled
        telemetry_hz=cfg.get("webdash", {}).get("telemetry_hz", 4.0),
    )

    print(f"[webdash] Serving on http://{args.host}:{args.port}")
    print(f"[webdash] Unauthenticated — LAN-only, demo-scoped.")
    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()
