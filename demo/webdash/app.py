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

try:
    from live.stage_taps import STAGE_NAMES
    _SPECTRO_OK = True
except ImportError:
    _SPECTRO_OK = False

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
:root{--bg:#111;--surface:#1e1e1e;--surface2:#171717;--border:#333;--text:#eee;--muted:#888;
  --green:#4caf50;--red:#f44336;--amber:#ff9800;--blue:#2196f3;--accent:#03a9f4;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;
  min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:12px;}
h1{font-size:1.05rem;letter-spacing:.05em;color:var(--muted);margin:0 0 4px;text-align:center;}
.wrap{width:100%;max-width:720px;}
.topbar{display:flex;justify-content:center;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;}
.src-badge{font-size:.7rem;padding:3px 10px;border-radius:12px;background:var(--surface2);
  color:var(--muted);border:1px solid var(--border);text-transform:uppercase;letter-spacing:.05em;}
.src-badge.replay{color:var(--accent);border-color:var(--accent);}
.tabs{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;}
.tab-btn{flex:1;padding:10px;border:1px solid var(--border);background:var(--surface2);color:var(--muted);
  border-radius:8px;cursor:pointer;font-weight:700;letter-spacing:.05em;font-size:.85rem;}
.tab-btn.active{background:var(--accent);color:#000;border-color:var(--accent);}
.tabpage{display:none;}
.tabpage.active{display:block;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:14px;width:100%;margin-bottom:10px;}
.card h2{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px;}
.row{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.row:last-child{margin-bottom:0;}
.label{color:var(--muted);font-size:.85rem;text-transform:uppercase;letter-spacing:.05em;}
.value{font-size:1.05rem;font-weight:600;}
.mode-badge{display:inline-block;padding:4px 14px;border-radius:20px;font-size:.9rem;
  font-weight:700;text-transform:uppercase;letter-spacing:.1em;}
.enhance{background:var(--green);color:#000;}
.bypass{background:var(--amber);color:#000;}
#toggle-btn{width:100%;padding:14px;border:none;border-radius:10px;font-size:1rem;
  font-weight:700;cursor:pointer;letter-spacing:.05em;margin-top:10px;}
.conf-bar-wrap{flex:1;margin-left:12px;background:var(--border);border-radius:4px;height:8px;}
.conf-bar{height:8px;border-radius:4px;background:var(--accent);transition:width .3s;}
.mos-box{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:4px;}
.mos-cell{text-align:center;padding:8px;background:var(--bg);border-radius:8px;}
.mos-cell .v{font-size:1.3rem;font-weight:700;}
.mos-cell .k{font-size:.75rem;color:var(--muted);}
.warn{color:var(--red);}
.ok{color:var(--green);}
.dim{color:var(--muted);}
#status{font-size:.75rem;color:var(--muted);text-align:center;margin-top:4px;margin-bottom:8px;}

/* Signal chain */
.chain{display:flex;gap:6px;overflow-x:auto;padding-bottom:4px;}
.stage-box{flex:1;min-width:82px;background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:8px 4px;text-align:center;}
.stage-box.off{opacity:.35;}
.stage-box .name{font-size:.62rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;}
.stage-box .lvl{font-size:.85rem;font-weight:700;margin-top:4px;}
.chain-arrow{align-self:center;color:var(--muted);font-size:.9rem;}

/* Spectrogram / heatmap canvases */
canvas.spec{width:100%;height:90px;background:#000;border-radius:6px;display:block;}
.spec-row{display:flex;gap:8px;margin-top:8px;}
.spec-col{flex:1;min-width:0;}
.spec-col .cap{font-size:.68rem;color:var(--muted);text-align:center;margin-bottom:4px;text-transform:uppercase;}
canvas.heat{width:100%;height:34px;border-radius:6px;display:block;}
.heat-legend{display:flex;justify-content:space-between;font-size:.65rem;color:var(--muted);margin-top:4px;}

/* Metrics grid */
.metric-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;}
.metric-cell{background:var(--bg);border-radius:8px;padding:8px;text-align:center;}
.metric-cell .v{font-size:1.15rem;font-weight:700;}
.metric-cell .k{font-size:.68rem;color:var(--muted);margin-top:2px;}
.metric-cell.grey{opacity:.4;}
.metric-cell .req{font-size:.58rem;color:var(--muted);margin-top:2px;}
.mode-note{font-size:.7rem;color:var(--muted);margin-top:8px;text-align:center;}

/* Compare tab */
select,button.plain{background:var(--surface2);color:var(--text);border:1px solid var(--border);
  border-radius:6px;padding:8px;font-size:.85rem;}
.compare-controls{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.compare-controls select{flex:1;min-width:120px;}
.compare-grid{display:grid;grid-template-columns:1fr;gap:8px;}
.method-card{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:10px;}
.method-card.ours{border-color:var(--accent);}
.method-card .mname{font-weight:700;font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;}
.method-card .mname.ours-tag::after{content:" (our model)";color:var(--accent);font-weight:400;text-transform:none;}
.method-card audio{width:100%;margin-top:6px;height:32px;}
.method-metrics{display:flex;gap:10px;margin-top:6px;font-size:.72rem;color:var(--muted);flex-wrap:wrap;}
.method-metrics b{color:var(--text);}

/* Record & Compare */
.rec-controls{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap;}
#rec-btn{padding:12px 20px;border:none;border-radius:10px;background:var(--red);color:#fff;
  font-weight:700;letter-spacing:.05em;cursor:pointer;font-size:.9rem;}
#rec-btn:disabled{opacity:.5;cursor:default;}
#rec-status{font-size:.8rem;color:var(--muted);}
.rec-note{font-size:.7rem;color:var(--muted);margin-bottom:10px;}
</style>
</head>
<body>
<div class="wrap">
<h1>PS26052 · ANC Live Dashboard</h1>
<div class="topbar">
  <span id="mode-badge" class="mode-badge enhance">ENHANCE</span>
  <span id="src-badge" class="src-badge">LIVE MIC</span>
</div>
<div id="status">Connecting…</div>

<div class="tabs">
  <button class="tab-btn active" id="tab-live-btn" onclick="showTab('live')">Live / Replay</button>
  <button class="tab-btn" id="tab-compare-btn" onclick="showTab('compare')">Compare Methods</button>
  <button class="tab-btn" id="tab-record-btn" onclick="showTab('record')">Record &amp; Compare</button>
</div>

<div class="tabpage active" id="tab-live">

  <div class="card">
    <button id="toggle-btn" onclick="toggleMode()">Switch to BYPASS</button>
  </div>

  <div class="card">
    <h2>Signal Chain (measured, per stage)</h2>
    <div class="chain" id="chain"></div>
  </div>

  <div class="card">
    <h2>Live Spectrum</h2>
    <div class="spec-row">
      <div class="spec-col"><div class="cap">Before (raw input)</div><canvas class="spec" id="spec-before"></canvas></div>
      <div class="spec-col"><div class="cap">After (enhanced output)</div><canvas class="spec" id="spec-after"></canvas></div>
    </div>
  </div>

  <div class="card">
    <h2>Per-Band Suppression (measured, capture → output)</h2>
    <canvas class="heat" id="heatmap"></canvas>
    <div class="heat-legend"><span>50 Hz</span><span>amplified ↑ / suppressed ↓</span><span>8 kHz</span></div>
  </div>

  <div class="card">
    <h2>Quality Metrics</h2>
    <div class="metric-grid" id="metric-grid"></div>
    <div class="mode-note" id="mode-note"></div>
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

</div>

<div class="tabpage" id="tab-compare">
  <div class="card">
    <h2>Classical DSP vs DeepFilterNet3 — audited eval results, no live processing</h2>
    <div class="compare-controls">
      <select id="cmp-category" onchange="cmpRefreshMixtures()"><option value="">All categories</option></select>
      <select id="cmp-mixture" onchange="cmpLoadMixture()"><option value="">Choose a mixture…</option></select>
    </div>
    <div class="compare-grid" id="cmp-grid"></div>
  </div>
</div>

<div class="tabpage" id="tab-record">
  <div class="card">
    <h2>Record a fresh clip from the real mic, run every method on it</h2>
    <div class="rec-note">
      No clean reference exists for a live recording, so SI-SNR/STOI/PESQ-WB can't be
      computed here (there's nothing to compare against). DNSMOS (non-intrusive) is shown
      instead. The oracle NLMS baseline is excluded — it needs an isolated noise-only
      reference that only exists for the offline corpus.
    </div>
    <div class="rec-controls">
      <select id="rec-duration">
        <option value="5">5s</option>
        <option value="10" selected>10s</option>
        <option value="15">15s</option>
        <option value="20">20s</option>
      </select>
      <button id="rec-btn" onclick="recStart()">● Record</button>
      <span id="rec-status"></span>
    </div>
    <div class="compare-grid" id="rec-grid"></div>
  </div>
</div>

</div>

<script>
let currentMode = "enhance";
let ws;
const STAGES = [
  ["capture","Capture"], ["pre_filter","Pre-filter"], ["dfn_core","DFN3"],
  ["residual","Residual"], ["output","Output"]
];
const N_BANDS = 64;

// ---- Signal chain boxes (built once) ----
const chainEl = document.getElementById("chain");
STAGES.forEach(([key,label]) => {
  const box = document.createElement("div");
  box.className = "stage-box off";
  box.id = "stage-" + key;
  box.innerHTML = '<div class="name">'+label+'</div><div class="lvl">OFF</div>';
  chainEl.appendChild(box);
});

// ---- Canvas setup (scrolling spectrogram via self-copy) ----
function setupCanvas(id) {
  const c = document.getElementById(id);
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth || 300, h = c.clientHeight || 90;
  c.width = w; c.height = h;
  return c;
}
let specBefore, specAfter, heatCanvas;
window.addEventListener("load", () => {
  specBefore = setupCanvas("spec-before");
  specAfter = setupCanvas("spec-after");
  heatCanvas = setupCanvas("heatmap");
});

function levelColor(norm) {
  // norm in [0,1] -> dark blue -> cyan -> yellow -> red
  const stops = [[0,0,40],[0,120,220],[0,220,180],[255,220,0],[255,40,0]];
  const t = Math.max(0, Math.min(1, norm)) * (stops.length - 1);
  const i = Math.floor(t), f = t - i;
  const a = stops[i], b = stops[Math.min(i+1, stops.length-1)];
  const r = Math.round(a[0]+(b[0]-a[0])*f), g = Math.round(a[1]+(b[1]-a[1])*f), bl = Math.round(a[2]+(b[2]-a[2])*f);
  return `rgb(${r},${g},${bl})`;
}

function drawSpecColumn(canvas, bins) {
  if (!canvas || !bins) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.drawImage(canvas, -1, 0);   // shift left by 1px
  const bandH = h / bins.length;
  for (let i = 0; i < bins.length; i++) {
    const norm = bins[i] / 255;
    ctx.fillStyle = levelColor(norm);
    // draw low freq at bottom, high freq at top
    ctx.fillRect(w - 1, h - (i + 1) * bandH, 1, Math.ceil(bandH) + 1);
  }
}

function drawHeatmap(canvas, db) {
  if (!canvas || !db) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const bandW = w / db.length;
  for (let i = 0; i < db.length; i++) {
    const v = db[i];   // dB delta, typically -40..+5
    let color;
    if (v >= 0) {
      const t = Math.min(1, v / 6);
      color = `rgb(${Math.round(255*t)},${Math.round(160*(1-t)+60*t)},60)`;   // amber->red for gain
    } else {
      const t = Math.min(1, -v / 30);
      color = `rgb(${Math.round(20*(1-t))},${Math.round(60+120*t)},${Math.round(120+120*t)})`;  // blue for suppression
    }
    ctx.fillStyle = color;
    ctx.fillRect(Math.floor(i * bandW), 0, Math.ceil(bandW) + 1, h);
  }
}

// ---- Metrics grid ----
const metricGrid = document.getElementById("metric-grid");
function renderMetrics(d) {
  const refOn = !!d.reference_available;
  const cells = [
    ["SI-SNR", d.si_snr, "dB", refOn],
    ["STOI", d.stoi, "", refOn],
    ["PESQ-WB", d.pesq_wb, "", refOn],
  ];
  metricGrid.innerHTML = "";
  cells.forEach(([label, val, unit, available]) => {
    const cell = document.createElement("div");
    cell.className = "metric-cell" + (available ? "" : " grey");
    if (available && val != null) {
      cell.innerHTML = `<div class="v">${val}${unit ? " "+unit : ""}</div><div class="k">${label}</div>`;
    } else if (available) {
      cell.innerHTML = `<div class="v dim">…</div><div class="k">${label}</div>`;
    } else {
      cell.innerHTML = `<div class="v dim">—</div><div class="k">${label}</div><div class="req">requires reference signal</div>`;
    }
    metricGrid.appendChild(cell);
  });
  const note = document.getElementById("mode-note");
  if (refOn) {
    note.textContent = "Reference-backed: true values over a " + (d.metrics_window_sec || "?") + "s sliding window.";
  } else {
    note.textContent = "Live mic has no clean reference — SI-SNR/STOI/PESQ-WB cannot be computed (they require one). Launch with --backup + --clean-ref for reference-replay mode.";
  }
}

function renderChain(levels) {
  STAGES.forEach(([key,label]) => {
    const box = document.getElementById("stage-" + key);
    const v = levels ? levels[key] : null;
    if (v == null) {
      box.className = "stage-box off";
      box.querySelector(".lvl").textContent = "OFF";
    } else {
      box.className = "stage-box";
      box.querySelector(".lvl").textContent = v.toFixed(0) + " dB";
    }
  });
}

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

    const srcBadge = document.getElementById("src-badge");
    if (d.reference_available) {
      srcBadge.textContent = "REFERENCE REPLAY";
      srcBadge.className = "src-badge replay";
    } else {
      srcBadge.textContent = "LIVE MIC";
      srcBadge.className = "src-badge";
    }

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

    renderChain(d.stage_levels_db);
    renderMetrics(d);
    if (specBefore) drawSpecColumn(specBefore, d.spectrum_before);
    if (specAfter) drawSpecColumn(specAfter, d.spectrum_after);
    if (heatCanvas) drawHeatmap(heatCanvas, d.suppression_db);
  };
}

function toggleMode() {
  const next = currentMode === "enhance" ? "bypass" : "enhance";
  fetch("/mode/" + next).catch(() => {});
}

function showTab(name) {
  ["live","compare","record"].forEach(n => {
    document.getElementById("tab-"+n).className = "tabpage" + (n===name ? " active" : "");
    document.getElementById("tab-"+n+"-btn").className = "tab-btn" + (n===name ? " active" : "");
  });
  if (name === "compare" && !window._cmpLoaded) { cmpInit(); window._cmpLoaded = true; }
}

// ---- Compare tab ----
let cmpAllMixtures = [];
async function cmpInit() {
  const r = await fetch("/compare/mixtures");
  if (!r.ok) { document.getElementById("cmp-grid").textContent = "Comparison data unavailable — run the eval pipeline first."; return; }
  const body = await r.json();
  cmpAllMixtures = body.mixtures;
  const cats = [...new Set(cmpAllMixtures.map(m => m.category))].sort();
  const catSel = document.getElementById("cmp-category");
  cats.forEach(c => { const o = document.createElement("option"); o.value = c; o.textContent = c; catSel.appendChild(o); });
  cmpRefreshMixtures();
}
function cmpRefreshMixtures() {
  const cat = document.getElementById("cmp-category").value;
  const sel = document.getElementById("cmp-mixture");
  sel.innerHTML = '<option value="">Choose a mixture…</option>';
  cmpAllMixtures.filter(m => !cat || m.category === cat).forEach(m => {
    const o = document.createElement("option");
    o.value = m.mixture_id;
    o.textContent = `${m.subtype} @ ${m.snr_db}dB (${m.mixture_id})`;
    sel.appendChild(o);
  });
}
async function cmpLoadMixture() {
  const mid = document.getElementById("cmp-mixture").value;
  const grid = document.getElementById("cmp-grid");
  if (!mid) { grid.innerHTML = ""; return; }
  const r = await fetch("/compare/metrics/" + encodeURIComponent(mid));
  if (!r.ok) { grid.textContent = "Metrics unavailable for this mixture."; return; }
  const m = await r.json();
  const order = ["noisy","nlms","spectral_subtraction","wiener", m.our_model_method];
  grid.innerHTML = "";
  order.forEach(method => {
    const row = m.methods[method];
    if (!row) return;
    const card = document.createElement("div");
    card.className = "method-card" + (method === m.our_model_method ? " ours" : "");
    const nameClass = method === m.our_model_method ? "mname ours-tag" : "mname";
    card.innerHTML = `
      <div class="${nameClass}">${method.replace(/_/g," ")}</div>
      <audio controls src="/compare/audio/${encodeURIComponent(mid)}/${encodeURIComponent(method)}"></audio>
      <div class="method-metrics">
        <span>SI-SNR <b>${row.si_snr != null ? row.si_snr.toFixed(2)+" dB" : "—"}</b></span>
        <span>STOI <b>${row.stoi != null ? row.stoi.toFixed(3) : "—"}</b></span>
        <span>PESQ-WB <b>${row.pesq_wb != null ? row.pesq_wb.toFixed(2) : "—"}</b></span>
      </div>`;
    grid.appendChild(card);
  });
}

// ---- Record & Compare tab ----
async function recStart() {
  const dur = parseInt(document.getElementById("rec-duration").value, 10);
  const btn = document.getElementById("rec-btn");
  const status = document.getElementById("rec-status");
  const grid = document.getElementById("rec-grid");
  btn.disabled = true;
  grid.innerHTML = "";
  let remaining = dur;
  status.textContent = `Recording… ${remaining}s`;
  const tick = setInterval(() => {
    remaining -= 1;
    status.textContent = remaining > 0 ? `Recording… ${remaining}s` : "Processing (classical DSP + DeepFilterNet3)…";
  }, 1000);
  try {
    const r = await fetch("/record/record?duration_sec=" + dur, { method: "POST" });
    clearInterval(tick);
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      status.textContent = "Failed: " + (body.detail || r.status);
      return;
    }
    const body = await r.json();
    status.textContent = `Done (${body.duration_sec}s clip).`;
    const order = ["noisy","spectral_subtraction","wiener","deepfilternet_tuned"];
    order.forEach(method => {
      const m = body.methods[method];
      if (!m) return;
      const card = document.createElement("div");
      card.className = "method-card" + (method === "deepfilternet_tuned" ? " ours" : "");
      const nameClass = method === "deepfilternet_tuned" ? "mname ours-tag" : "mname";
      const dnsmosHtml = m.dnsmos
        ? `<span>DNSMOS OVR <b>${m.dnsmos.ovr}</b></span><span>SIG <b>${m.dnsmos.sig}</b></span><span>BAK <b>${m.dnsmos.bak}</b></span>`
        : `<span>DNSMOS unavailable — see models/dnsmos/download_model.py</span>`;
      card.innerHTML = `
        <div class="${nameClass}">${method.replace(/_/g," ")}</div>
        <audio controls src="/record/audio/${encodeURIComponent(body.recording_id)}/${encodeURIComponent(method)}"></audio>
        <div class="method-metrics">${dnsmosHtml}</div>`;
      grid.appendChild(card);
    });
  } catch (e) {
    clearInterval(tick);
    status.textContent = "Failed: " + e;
  } finally {
    btn.disabled = false;
  }
}

connect();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Telemetry builder
# ---------------------------------------------------------------------------
def _build_telemetry(pipeline, telemetry=None, stage_metrics=None) -> dict:
    """Build JSON-safe telemetry dict from pipeline display hooks + Phase 4 telemetry
    + Phase "dashboard" per-stage metrics/spectra (live/stage_metrics.py)."""
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
        "reference_available": bool(getattr(pipeline, "reference_available", False)),
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

    # Everything below (per-stage levels, suppression map, and the quantised
    # BEFORE/AFTER display spectra) is computed ONCE per tick by
    # live/stage_metrics.py's background thread and merely read here.
    #
    # It used to compute the two spectra inline, per connected client, per
    # frame. On the Pi with 3 browsers open at 4 Hz that was ~24 FFT+binning
    # passes/sec inside the asyncio loop, competing with the real-time
    # inference thread for the GIL -- confirmed cause of audible breakup on
    # Pi 5, 2026-09-05. Reading a cached value makes the cost constant in the
    # number of viewers.
    if stage_metrics is not None:
        payload.update(stage_metrics.snapshot())
    else:
        payload.update({
            "stage_levels_db": {name: None for name in (STAGE_NAMES if _SPECTRO_OK else [])},
            "suppression_db": None,
            "metrics_mode": "non_intrusive",
            "si_snr": None, "stoi": None, "pesq_wb": None, "metrics_window_sec": None,
            "spectrum_before": None, "spectrum_after": None,
        })

    return payload


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------
def make_app(pipeline, telemetry=None, telemetry_hz: float = 4.0, stage_metrics=None,
             compare_app=None, record_app=None):
    """
    Build and return the FastAPI application.

    Parameters
    ----------
    pipeline   : object with ._mode (str, r/w), .last_in_chunk, .last_out_chunk,
                 ._chunk_latencies (list[float]), ._chunk_sec (float)
    telemetry  : PipelineTelemetry or None — Phase 4 noise/MOS fields
    telemetry_hz : WebSocket push rate in Hz (default 4)
    stage_metrics : live.stage_metrics.StageMetrics or None — per-stage levels,
                 suppression heatmap, and reference-backed intrusive metrics
    compare_app : optional FastAPI sub-app (demo/webdash/compare.py) mounted
                 at /compare for the offline classical-vs-AI comparison mode
    """
    if not _FASTAPI_OK:
        raise ImportError(
            "fastapi is required for the web dashboard. "
            "Install it: pip install fastapi uvicorn[standard]"
        )

    app = FastAPI(title="PS26052 Live Dashboard", docs_url=None, redoc_url=None)
    _interval = 1.0 / max(telemetry_hz, 0.5)

    if compare_app is not None:
        app.mount("/compare", compare_app)
    if record_app is not None:
        app.mount("/record", record_app)

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
                payload = _build_telemetry(pipeline, telemetry, stage_metrics)
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

    # 5. WebSocket emits valid JSON with required keys, including the
    # dashboard-rebuild fields (defaults, since stage_metrics=None here)
    with client.websocket_connect("/ws") as ws:
        raw = ws.receive_text()
        payload = json.loads(raw)
        for key in ("ts", "mode", "rtf", "latency_ms", "noise_category", "mos_valid",
                    "stage_levels_db", "suppression_db", "metrics_mode",
                    "reference_available", "si_snr", "stoi", "pesq_wb",
                    "spectrum_before", "spectrum_after"):
            assert key in payload, f"telemetry missing key {key!r}"
        assert payload["mode"] == "enhance"
        assert isinstance(payload["rtf"], float)
        assert payload["mos_valid"] is False
        assert payload["reference_available"] is False
        assert payload["si_snr"] is None, "no stage_metrics wired -> must not fabricate a value"
        assert payload["spectrum_before"] is None, "MockPipeline has no stage_taps -> no spectrum"

    # 6. With a real StageMetrics wired to a pipeline that DOES expose
    # stage_taps + reference_available, the payload carries real computed
    # levels/spectra instead of the all-None defaults.
    from live.stage_taps import StageTaps
    from live.stage_metrics import StageMetrics

    class _MockPipelineWithTaps(_MockPipeline):
        _sr = 48000
        reference_available = False
        current_clean_ref_chunk = None

        def __init__(self):
            self.stage_taps = StageTaps()

    pipe2 = _MockPipelineWithTaps()
    import numpy as _np
    pipe2.stage_taps.capture = (0.3 * _np.ones(4800, dtype=_np.float32))
    pipe2.stage_taps.output = (0.1 * _np.ones(4800, dtype=_np.float32))
    sm = StageMetrics(pipe2, cadence_sec=0.01, window_sec=0.5, poll_sec=0.005)
    # Run synchronously -- no need for the background thread here.
    sm._update_levels()
    sm._update_spectra_and_suppression()

    app2 = make_app(pipe2, telemetry=None, telemetry_hz=4.0, stage_metrics=sm)
    client2 = TestClient(app2, raise_server_exceptions=True)
    with client2.websocket_connect("/ws") as ws:
        raw = ws.receive_text()
        payload = json.loads(raw)
        assert payload["stage_levels_db"]["capture"] is not None
        assert payload["stage_levels_db"]["pre_filter"] is None, "untapped stage must stay OFF (None)"
        assert payload["suppression_db"] is not None and len(payload["suppression_db"]) == 64
        assert payload["spectrum_before"] is not None and len(payload["spectrum_before"]) == 64
        assert all(0 <= v <= 255 for v in payload["spectrum_before"]), "spectrum must be quantised to uint8 range"

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
    parser.add_argument(
        "--clean-ref",
        default=None,
        metavar="WAV_PATH",
        help="Dashboard reference-replay mode (Mode 2): clean reference WAV sample-aligned "
             "with --backup's mixture. Only takes effect together with --backup. Unlocks true "
             "SI-SNR/STOI/PESQ-WB on the dashboard instead of greyed-out 'requires reference' cells.",
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
    from live.telemetry import PipelineTelemetry
    from live.stage_metrics import StageMetrics
    cfg = _load_config("config/audio_config.yaml")

    pipeline = LivePipeline(cfg, backup_audio_path=args.backup, clean_ref_path=args.clean_ref)
    pipeline.start()

    telemetry = PipelineTelemetry()

    clf_cfg = cfg.get("noise_classifier", {})
    if clf_cfg.get("enabled", False):
        from models.noise_classifier.classify_chunk import NoiseClassifier
        classifier = NoiseClassifier(
            clf_cfg.get("model_path", "models/noise_classifier/model.pt"),
            threshold=clf_cfg.get("confidence_threshold", 0.6),
            cadence_sec=clf_cfg.get("cadence_sec", 0.5),
        )
        classifier.start(pipeline, telemetry)
        print("[webdash] Noise classifier thread started.")

    dnsmos_cfg = cfg.get("dnsmos", {})
    if dnsmos_cfg.get("enabled", False):
        from models.dnsmos.dnsmos_infer import DNSMOSMonitor
        monitor = DNSMOSMonitor(
            telemetry, pipeline,
            model_dir=dnsmos_cfg.get("model_dir", "models/dnsmos"),
            cadence_sec=dnsmos_cfg.get("cadence_sec", 2.0),
            window_sec=dnsmos_cfg.get("window_sec", 9.01),
            warn_threshold=dnsmos_cfg.get("warn_threshold", 2.5),
            auto_bypass=dnsmos_cfg.get("auto_bypass", False),
        )
        monitor.start()
        print("[webdash] DNSMOS monitor thread started.")

    stage_metrics = StageMetrics(pipeline, cadence_sec=1.0, window_sec=3.0)
    stage_metrics.start()
    print("[webdash] Stage metrics thread started (per-stage levels, suppression heatmap"
          + (", reference-backed SI-SNR/STOI/PESQ-WB" if pipeline.reference_available else "") + ").")

    compare_app = None
    try:
        from demo.webdash.compare import make_compare_app
        compare_app = make_compare_app()
        print("[webdash] Method comparison mode mounted at /compare.")
    except Exception as exc:
        print(f"[webdash] Comparison mode unavailable: {exc}")

    record_app = None
    try:
        from demo.webdash.record_compare import make_record_app
        # Record & Compare captures from the live pipeline's EXISTING capture
        # tap (record_from_pipeline), not by opening the input device again.
        # Confirmed on Pi 5 2026-09-05: ALSA refuses a second concurrent open
        # of a device the live stream already holds -- every /record request
        # 500'd with PaErrorCode -9985 "Device unavailable". The `device`
        # argument below is only used in the standalone/no-pipeline case.
        record_app = make_record_app(
            device=cfg["audio"].get("input_device", None),
            sample_rate=int(cfg["audio"]["sample_rate"]),
            atten_lim_db=float(cfg["model"].get("atten_lim_db", 30.0)),
            pipeline=pipeline,
        )
        print("[webdash] Record & Compare mode mounted at /record.")
    except Exception as exc:
        print(f"[webdash] Record & Compare mode unavailable: {exc}")

    app = make_app(
        pipeline,
        telemetry=telemetry,
        telemetry_hz=cfg.get("webdash", {}).get("telemetry_hz", 4.0),
        stage_metrics=stage_metrics,
        compare_app=compare_app,
        record_app=record_app,
    )

    print(f"[webdash] Serving on http://{args.host}:{args.port}")
    print(f"[webdash] Unauthenticated — LAN-only, demo-scoped.")
    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()
