#!/usr/bin/env python3
"""
Generates an interactive HTML trace visualization from Plume timestamps.txt files.

Usage:
    python trace_viewer.py <folder1> [<folder2> ...] [-o output.html]

Each folder must contain a timestamps.txt file.
"""

import sys
import json
import os
import argparse
import colorsys

RECORD_POINTS = [
    "DeserializationEnd", "EnterDispatcher",
    "DynamicParsingEnd", "ShardingStart", 
    "IOQueueStart", "IOQueueEnd",
    "ComputeQueueStart", "ComputeQueueEnd",
    "MasterFetchStart", "MasterFetchEnd",
    "RemoteTake",
    "RemoteIOQueueStart", "RemoteIOQueueEnd",
    "RemoteComputeQueueStart", "RemoteComputeQueueEnd",
    "FetchingStart", "FetchingEnd",
    "ParsingStart", "ParsingEnd",
    "LoadStart", "TransferStart",
    "EngineStart", "EngineEnd",
    "FutureReturn",
]

PHASES_DEF = [
    ("input deserialization","Input Deserialization",  110),
    ("composition parsing",  "Compostion Parsing",     280),
    ("sharding",             "Sharding",               150),
    ("io_queue",             "IO Queue",               335),
    ("compute_queue",        "Compute Queue",          300),
    ("remote_routing",       "Remote Routing",         260),
    ("remote_io_queue",      "Remote IO Queue",        335),
    ("remote_compute_queue", "Remote Compute Queue",   300),
    ("master_fetch",         "Master Fetch",           210),
    ("fetch",                "Fetch Inputs",           210),
    ("parse",                "Parse Binary",            60),
    ("load",                 "Load Binary",             42),
    ("transfer",             "Transfer Inputs",         25),
    ("execute",              "Execute",                140),
]


def hls_to_hex(h, l, s):
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"


def phase_color(hue, pct):
    h = hue / 360
    l = 0.35 + 0.5 * (pct / 100)
    return hls_to_hex(h, l, 0.85)


PHASE_META = {
    key: {"label": label, "face": phase_color(hue, 100), "edge": phase_color(hue, 0)}
    for key, label, hue in PHASES_DEF
}


def rp(ts, name):
    return ts[RECORD_POINTS.index(name)] / 1000


def find_slot(start, end, busy_until):
    for i, t in enumerate(busy_until):
        if start > t:
            busy_until[i] = end
            return i
    busy_until.append(end)
    return len(busy_until) - 1


def extract_invocations(node, parent_group_id, results, group_counter,
                        group_index=None, child_index=None):
    """Collect invocations without slot assignment (slots assigned after sorting).

    The parent's children is a list of lists. group_index is which sub-list the
    node lives in and child_index is its position within that sub-list (both None
    for the root); together they disambiguate non-unique ids as "group-child".
    """
    # if node["id"] not in ("Composition", "HTTP"):
    ts = node["ts"]

    ds_e   = rp(ts, "DeserializationEnd")
    sh_s   = rp(ts, "ShardingStart")
    cp_e   = rp(ts, "DynamicParsingEnd")
    io_qs  = rp(ts, "IOQueueStart");     io_qe  = rp(ts, "IOQueueEnd")
    cq_s   = rp(ts, "ComputeQueueStart"); cq_e  = rp(ts, "ComputeQueueEnd")
    mf_s   = rp(ts, "MasterFetchStart"); mf_e   = rp(ts, "MasterFetchEnd")
    rt     = rp(ts, "RemoteTake")
    rio_qs = rp(ts, "RemoteIOQueueStart"); rio_qe = rp(ts, "RemoteIOQueueEnd")
    rcq_s  = rp(ts, "RemoteComputeQueueStart"); rcq_e = rp(ts, "RemoteComputeQueueEnd")
    fe_s   = rp(ts, "FetchingStart");    fe_e   = rp(ts, "FetchingEnd")
    pa_s   = rp(ts, "ParsingStart");     pa_e   = rp(ts, "ParsingEnd")
    lo_s   = rp(ts, "LoadStart")
    tr_s   = rp(ts, "TransferStart")
    ex_s   = rp(ts, "EngineStart");      ex_e   = rp(ts, "EngineEnd")
    done   = rp(ts, "FutureReturn")

    if io_qs > io_qe:
        io_qs = io_qe

    candidates = [io_qs, mf_s, cq_s, rt, fe_s, pa_s, lo_s, tr_s, ex_s]
    start = next((c for c in candidates if c > 0), ex_s)
    end = done if done > 0 else ex_e

    phases = {}
    if ds_e > 0:   phases["input deserialization"] = [0, ds_e]
    if cp_e > 0:   phases["composition parsing"]   = [ds_e, cp_e]
    if sh_s > 0:   phases["sharding"]              = [sh_s, io_qs]
    if io_qs > 0:  phases["io_queue"]              = [io_qs, io_qe]
    if cq_s > 0:   phases["compute_queue"]         = [cq_s, cq_e]
    if mf_s > 0:   phases["master_fetch"]          = [mf_s, mf_e]
    if rt > 0 and rio_qs > 0: phases["remote_routing"] = [rt, rio_qs]
    if rio_qs > 0: phases["remote_io_queue"]       = [rio_qs, rio_qe]
    if rcq_s > 0:  phases["remote_compute_queue"]  = [rcq_s, rcq_e]
    if fe_s > 0:   phases["fetch"]                 = [fe_s, fe_e]
    if pa_s > 0:   phases["parse"]                 = [pa_s, pa_e]
    if lo_s > 0:   phases["load"]                  = [lo_s, tr_s if tr_s > 0 else ex_s]
    if tr_s > 0:   phases["transfer"]              = [tr_s, ex_s]
    phases["execute"] = [ex_s, ex_e]

    def r3(v): return round(v, 3)

    results.append({
        "id": node["id"],
        "group_index": group_index,
        "child_index": child_index,
        "group": parent_group_id,
        "slot": 0,  # assigned in assign_slots()
        "start": r3(start),
        "end": r3(end),
        "on_remote": rt > 0,
        "node_id": node.get("node id"),
        "items": node.get("items", 0),
        "input_size": node.get("input size", 0),
        "phases": {k: [r3(v[0]), r3(v[1])] for k, v in phases.items()},
    })

    for group_idx, group in enumerate(node.get("children", [])):
        if not group:
            continue
        gid = group_counter[0]
        group_counter[0] += 1
        for child_idx, child in enumerate(group):
            extract_invocations(child, gid, results, group_counter, group_idx, child_idx)


def assign_slots(results):
    """Sort by (group tree-order, end time) then pack greedily into slots."""
    results.sort(key=lambda x: (x["group"] if x["group"] is not None else float("inf"), -(x["end"] - x["start"])))
    busy_until = []
    for inv in results:
        inv["slot"] = find_slot(inv["start"], inv["end"], busy_until)
    return (max(r["slot"] for r in results) + 1) if results else 1


def parse_folder(folder_path):
    ts_file = os.path.join(folder_path, "timestamps.txt")
    if not os.path.exists(ts_file):
        sys.exit(f"Error: {ts_file} not found")

    with open(ts_file) as f:
        content = f.read()

    queries = {}
    for block in content.strip().split("\nQuery "):
        block = block.strip()
        if not block:
            continue
        block = block.removeprefix("Query ")
        colon = block.index(":")
        raw_name = block[:colon].strip()
        name = raw_name.replace("TPCH_Q", "q")
        json_str = block[colon + 1:].strip()
        runs = json.loads(json_str)
        if isinstance(runs, list):
            if len(runs) == 0:
                continue
            run_list = runs
        else:
            run_list = [runs]

        runs_data = []
        for run in run_list:
            results = []
            group_counter = [0]
            extract_invocations(run, None, results, group_counter)
            num_slots = assign_slots(results)
            max_time = max((r["end"] for r in results), default=0)
            group_sizes = {}
            for r in results:
                if r["group"] is not None:
                    group_sizes[r["group"]] = group_sizes.get(r["group"], 0) + 1
            for r in results:
                r["group_size"] = group_sizes.get(r["group"], 1) if r["group"] is not None else None
            runs_data.append({
                "invocations": results,
                "num_slots": num_slots,
                "max_time": round(max_time, 3),
            })
        queries[name] = {"runs": runs_data}

    return queries


def generate_html(traces, output_path):
    """traces: list of (folder_name, queries_dict)"""

    all_query_names = []
    seen = set()
    for _, queries in traces:
        for name in sorted(queries.keys(), key=lambda x: int(x[1:]) if x[1:].isdigit() else 999):
            if name not in seen:
                all_query_names.append(name)
                seen.add(name)

    # Build JS data structure
    js_traces = []
    for folder_name, queries in traces:
        js_queries = {}
        for qname, qdata in queries.items():
            js_queries[qname] = qdata
        js_traces.append({"name": folder_name, "queries": js_queries})

    phase_order = [p[0] for p in PHASES_DEF]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Plume Trace Viewer</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: #fff; color: #333; font: 12px/1.4 'SF Mono', 'Fira Code', monospace; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}
#tabs {{ display: flex; padding: 6px 8px 0; gap: 3px; overflow-x: auto; flex-shrink: 0; border-bottom: 1px solid #ddd; background: #f4f4f4; }}
#tabs::-webkit-scrollbar {{ height: 4px; }}
#tabs::-webkit-scrollbar-track {{ background: #f4f4f4; }}
#tabs::-webkit-scrollbar-thumb {{ background: #ccc; border-radius: 2px; }}
.tab {{ padding: 4px 10px; cursor: pointer; border-radius: 4px 4px 0 0; border: 1px solid #ccc; border-bottom: none; background: #f4f4f4; color: #888; font-size: 11px; white-space: nowrap; transition: background 0.1s; }}
.tab:hover {{ background: #ebebeb; color: #333; }}
.tab.active {{ background: #fff; color: #5c35cc; border-color: #5c35cc; }}
#controls {{ display: flex; align-items: center; gap: 14px; padding: 4px 10px; border-bottom: 1px solid #e8e8e8; flex-shrink: 0; background: #fafafa; font-size: 11px; color: #666; }}
#controls label {{ display: flex; align-items: center; gap: 6px; }}
#rowh-slider {{ width: 90px; accent-color: #5c35cc; cursor: pointer; }}
#fit-btn {{ padding: 2px 8px; border: 1px solid #ccc; border-radius: 3px; background: #fff; color: #555; font: 11px/1.4 'SF Mono', 'Fira Code', monospace; cursor: pointer; }}
#fit-btn:hover {{ background: #f0f0f0; }}
#run-wrap {{ display: flex; align-items: center; gap: 6px; }}
#run-select {{ padding: 2px 4px; border: 1px solid #ccc; border-radius: 3px; background: #fff; color: #555; font: 11px/1.4 'SF Mono', 'Fira Code', monospace; cursor: pointer; accent-color: #5c35cc; }}
#scroll-area {{ flex: 1; overflow: hidden; min-height: 0; display: flex; flex-direction: column; }}
#main {{ flex: 1; min-height: 0; display: flex; flex-direction: column; }}
.trace-section {{ flex: 1; min-height: 0; overflow-y: auto; border-top: 1px solid #e8e8e8; }}
.trace-section:first-child {{ border-top: none; }}
.trace-label {{ padding: 4px 10px; font-size: 12px; font-weight: bold; color: #555; background: #f8f8f8; border-bottom: 1px solid #e8e8e8; letter-spacing: 0.05em; position: sticky; top: 0; z-index: 1; }}
canvas {{ display: block; width: 100%; }}
#node-legend {{ display: none; flex-wrap: wrap; gap: 4px 14px; padding: 4px 12px; border-top: 1px solid #e8e8e8; flex-shrink: 0; background: #f4f4f4; align-items: center; }}
#node-legend-label {{ font-size: 10px; color: #aaa; margin-right: 2px; }}
#legend {{ display: flex; flex-wrap: wrap; gap: 4px 14px; padding: 6px 12px; border-top: 1px solid #e8e8e8; flex-shrink: 0; background: #f4f4f4; }}
.legend-item {{ display: flex; align-items: center; gap: 4px; font-size: 10px; color: #555; cursor: pointer; padding: 2px 5px; border-radius: 3px; border: 1px solid transparent; user-select: none; }}
.legend-item:hover {{ background: #ebebeb; }}
.legend-item.active {{ background: #ede9ff; border-color: #5c35cc; color: #3d1fa8; font-weight: bold; }}
.legend-swatch {{ width: 12px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
#hint {{ padding: 3px 12px; font-size: 10px; color: #bbb; border-top: 1px solid #f0f0f0; flex-shrink: 0; background: #fff; }}
#tooltip {{
  position: fixed; background: #fff; border: 1px solid #ccc;
  padding: 8px 10px; border-radius: 6px; font-size: 11px; pointer-events: none;
  display: none; max-width: 320px; z-index: 100; box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}}
.tt-title {{ color: #5c35cc; font-weight: bold; margin-bottom: 4px; }}
.tt-row {{ display: flex; justify-content: space-between; gap: 16px; padding: 1px 0; }}
.tt-label {{ color: #888; }}
.tt-val {{ color: #333; }}
.tt-phase-row {{ display: flex; align-items: center; gap: 6px; padding: 1px 0; }}
.tt-dot {{ width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }}
.tt-phase-dur {{ color: #166534; margin-left: auto; }}
.tt-sep {{ border: none; border-top: 1px solid #e8e8e8; margin: 4px 0; }}
</style>
</head>
<body>
<div id="tabs"></div>
<div id="controls">
  <label>Row height: <span id="rowh-val">5</span>px &nbsp;<input type="range" id="rowh-slider" min="2" max="40" value="5" step="1"></label>
  <button id="fit-btn">Fit all</button>
  <div id="run-wrap"><label for="run-select">Run:</label><select id="run-select"></select></div>
</div>
<div id="scroll-area"><div id="main"></div></div>
<div id="node-legend"></div>
<div id="legend"></div>
<div id="hint">Scroll to pan vertically &nbsp;·&nbsp; Cmd/Ctrl+scroll to zoom &nbsp;·&nbsp; Shift+scroll to adjust row height &nbsp;·&nbsp; Drag to pan &nbsp;·&nbsp; Click bar to highlight group &nbsp;·&nbsp; Click legend/node to filter &nbsp;·&nbsp; R to reset &nbsp;·&nbsp; Esc to clear</div>
<div id="tooltip"></div>
<script>
const TRACES = {json.dumps(js_traces)};
const QUERY_NAMES = {json.dumps(all_query_names)};
const PHASE_ORDER = {json.dumps(phase_order)};
const PHASE_META = {json.dumps(PHASE_META)};

let rowH = 5;
const AXIS_H = 24;
const PAD_L = 8;
const PAD_R = 8;
const REMOTE_ALPHA = 0.08;

// Shared view state — all canvases for the same query are synced
let activeRun = 0;

function queryMaxTime(name) {{
  return Math.max(1, ...TRACES.map(t => t.queries[name]?.runs[activeRun]?.max_time || 0));
}}
let sharedMaxTime = queryMaxTime(QUERY_NAMES[0]);
let sharedView = {{ start: 0, duration: sharedMaxTime * 1.02 }};

function clampView() {{
  sharedView.duration = Math.max(10, Math.min(sharedMaxTime * 1.02, sharedView.duration));
  sharedView.start = Math.max(0, sharedView.start);
  const maxStart = Math.max(0, sharedMaxTime - sharedView.duration);
  if (sharedView.start > maxStart) sharedView.start = maxStart;
}}

let selectedGroup = null;
let selectedPhase = null;
let selectedNode = null;
let activeQuery = QUERY_NAMES[0];

function clearFilter() {{
  selectedGroup = null;
  selectedPhase = null;
  selectedNode = null;
  document.querySelectorAll('.legend-item').forEach(li => li.classList.remove('active'));
}}

function fmtBytes(b) {{
  if (!b) return null;
  if (b >= 1048576) return (b / 1048576).toFixed(2) + ' MB';
  if (b >= 1024)    return (b / 1024).toFixed(1) + ' KB';
  return b + ' B';
}}

// ── Build tabs ──────────────────────────────────────────────────────────────
const tabsEl = document.getElementById('tabs');
QUERY_NAMES.forEach(name => {{
  const t = document.createElement('div');
  t.className = 'tab' + (name === activeQuery ? ' active' : '');
  t.textContent = name;
  t.addEventListener('click', () => setQuery(name));
  tabsEl.appendChild(t);
}});

// ── Build legend ─────────────────────────────────────────────────────────────
const legendEl = document.getElementById('legend');
PHASE_ORDER.forEach(key => {{
  const m = PHASE_META[key];
  const item = document.createElement('div');
  item.className = 'legend-item';
  item.dataset.phase = key;
  item.innerHTML = `<div class="legend-swatch" style="background:${{m.face}};border:1px solid ${{m.edge}}"></div>${{m.label}}`;
  item.addEventListener('click', () => {{
    if (selectedPhase === key) {{
      clearFilter();
    }} else {{
      clearFilter();
      selectedPhase = key;
      item.classList.add('active');
    }}
    redrawAll();
  }});
  legendEl.appendChild(item);
}});

// ── Node legend (rebuilt per query) ─────────────────────────────────────────
function buildNodeLegend() {{
  const nodeEl = document.getElementById('node-legend');
  nodeEl.innerHTML = '';
  const allInvs = TRACES.flatMap(t => t.queries[activeQuery]?.runs[activeRun]?.invocations || []);
  const nodeIds = [...new Set(allInvs
    .map(inv => inv.node_id)
    .filter(id => id !== null && id !== undefined)
  )].sort((a, b) => a - b);
  if (nodeIds.length === 0) {{ nodeEl.style.display = 'none'; return; }}
  nodeEl.style.display = 'flex';
  const lbl = document.createElement('span');
  lbl.id = 'node-legend-label';
  lbl.textContent = 'Nodes:';
  nodeEl.appendChild(lbl);
  nodeIds.forEach((nid) => {{
    const item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = `Node ${{nid}}`;
    item.addEventListener('click', () => {{
      if (selectedNode === nid) {{
        clearFilter();
      }} else {{
        clearFilter();
        selectedNode = nid;
        item.classList.add('active');
      }}
      redrawAll();
    }});
    nodeEl.appendChild(item);
  }});
}}

// ── Vertical zoom (row height) ───────────────────────────────────────────────
function setRowH(newH) {{
  const rounded = newH > rowH ? Math.ceil(newH) : Math.floor(newH);
  rowH = Math.max(2, Math.min(40, rounded));
  document.getElementById('rowh-val').textContent = rowH;
  document.getElementById('rowh-slider').value = rowH;
  resizeAndRedrawAll();
}}

document.getElementById('rowh-slider').addEventListener('input', e => {{
  setRowH(parseInt(e.target.value));
}});

document.getElementById('fit-btn').addEventListener('click', () => {{
  // rowH that makes all slots visible within each section's viewport height
  let minFitH = Infinity;
  document.querySelectorAll('.trace-section').forEach(sec => {{
    const c = sec.querySelector('canvas');
    if (!c) return;
    const m = c.id.match(/canvas-(\\d+)/);
    if (!m) return;
    const qdata = TRACES[parseInt(m[1])]?.queries[activeQuery]?.runs[activeRun];
    if (!qdata) return;
    const viewportH = sec.clientHeight - (sec.querySelector('.trace-label')?.offsetHeight || 0);
    minFitH = Math.min(minFitH, (viewportH - AXIS_H) / qdata.num_slots);
  }});
  if (isFinite(minFitH)) setRowH(minFitH);
}});

function resizeAndRedrawAll() {{
  document.querySelectorAll('.trace-section canvas').forEach(c => {{
    const m = c.id.match(/canvas-(\\d+)/);
    if (!m) return;
    const qdata = TRACES[parseInt(m[1])]?.queries[activeQuery]?.runs[activeRun];
    if (!qdata) return;
    c.height = qdata.num_slots * rowH + AXIS_H;
    drawCanvas(c, qdata);
  }});
}}

// On window resize, update canvas widths only (height is content-driven)
function resizeCanvases() {{
  document.querySelectorAll('.trace-section canvas').forEach(c => {{
    const newW = Math.floor(c.getBoundingClientRect().width);
    if (!newW) return;
    c.width = newW;
    const m = c.id.match(/canvas-(\\d+)/);
    if (!m) return;
    const qdata = TRACES[parseInt(m[1])]?.queries[activeQuery]?.runs[activeRun];
    if (qdata) drawCanvas(c, qdata);
  }});
}}

// ── Global drag state (one handler, not per-canvas) ─────────────────────────
let drag = null; // {{ canvasId, startX, startViewStart, vs, canvas, qdata }}

window.addEventListener('mousemove', e => {{
  if (!drag || !(e.buttons & 1)) {{ drag = null; return; }}
  const drawW = drag.canvas.width - PAD_L - PAD_R;
  const dx = e.clientX - drag.startX;
  sharedView.start = drag.startViewStart - (dx / drawW) * sharedView.duration;
  clampView();
  redrawAll();
}});
window.addEventListener('mouseup', () => {{ drag = null; }});

// ── Run dropdown ─────────────────────────────────────────────────────────────
function buildRunDropdown() {{
  const wrap = document.getElementById('run-wrap');
  const sel = document.getElementById('run-select');
  const count = Math.max(...TRACES.map(t => t.queries[activeQuery]?.runs?.length || 0));
  sel.innerHTML = '';
  for (let i = 0; i < count; i++) {{
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = `Run ${{i + 1}}`;
    sel.appendChild(opt);
  }}
  sel.value = activeRun;
  wrap.style.display = count > 1 ? 'flex' : 'none';
}}

document.getElementById('run-select').addEventListener('change', e => {{
  activeRun = parseInt(e.target.value);
  sharedMaxTime = queryMaxTime(activeQuery);
  sharedView = {{ start: 0, duration: sharedMaxTime * 1.02 }};
  clearFilter();
  buildNodeLegend();
  renderMain();
}});

// ── Query switcher ───────────────────────────────────────────────────────────
function setQuery(name) {{
  activeQuery = name;
  activeRun = 0;
  tabsEl.querySelectorAll('.tab').forEach((t, i) => {{
    t.classList.toggle('active', QUERY_NAMES[i] === name);
  }});
  clearFilter();
  sharedMaxTime = queryMaxTime(name);
  sharedView = {{ start: 0, duration: sharedMaxTime * 1.02 }};
  buildRunDropdown();
  buildNodeLegend();
  renderMain();
}}

// ── Main render ──────────────────────────────────────────────────────────────
function renderMain() {{
  const main = document.getElementById('main');
  // Reuse or recreate sections
  const sections = [];
  TRACES.forEach((trace, ti) => {{
    const qdata = trace.queries[activeQuery]?.runs[activeRun];
    if (!qdata || qdata.invocations.length === 0) return;
    sections.push({{trace, qdata, ti}});
  }});

  // Clear and rebuild if trace count changed
  const existing = main.querySelectorAll('.trace-section');
  if (existing.length !== sections.length) {{
    main.innerHTML = '';
    sections.forEach(({{trace, qdata, ti}}) => {{
      const sec = document.createElement('div');
      sec.className = 'trace-section';
      if (TRACES.length > 1) {{
        const lbl = document.createElement('div');
        lbl.className = 'trace-label';
        lbl.textContent = trace.name;
        sec.appendChild(lbl);
      }}
      const canvas = document.createElement('canvas');
      canvas.id = `canvas-${{ti}}`;
      sec.appendChild(canvas);
      main.appendChild(sec);
      setupCanvas(canvas, qdata, ti);
    }});
  }} else {{
    sections.forEach(({{trace, qdata, ti}}, si) => {{
      const sec = existing[si];
      const canvas = sec.querySelector('canvas');
      canvas.id = `canvas-${{ti}}`;
      setupCanvas(canvas, qdata, ti);
    }});
  }}
  buildNodeLegend();
  // After DOM is updated, sync canvas bitmap sizes to their CSS-rendered sizes
  requestAnimationFrame(resizeCanvases);
}}

function setupCanvas(canvas, qdata, traceIdx) {{
  canvas.width = canvas.parentElement.clientWidth || window.innerWidth;
  canvas.height = qdata.num_slots * rowH + AXIS_H;
  attachEvents(canvas, qdata, traceIdx);
}}

function drawCanvas(canvas, qdata) {{
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const drawW = W - PAD_L - PAD_R;
  const {{ start, duration }} = sharedView;

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, W, H);

  // Axis
  ctx.fillStyle = '#f8f8f8';
  ctx.fillRect(0, 0, W, AXIS_H);

  // Grid lines
  const nTicks = Math.max(4, Math.floor(drawW / 80));
  const rawStep = duration / nTicks;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const niceSteps = [1, 2, 5, 10];
  const step = niceSteps.map(s => s * magnitude).find(s => s >= rawStep) || rawStep;
  const tickStart = Math.ceil(start / step) * step;

  ctx.strokeStyle = '#e8e8e8';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#999';
  ctx.font = '10px SF Mono, Fira Code, monospace';
  ctx.textAlign = 'center';

  for (let t = tickStart; t < start + duration; t += step) {{
    const x = PAD_L + ((t - start) / duration) * drawW;
    if (x < PAD_L || x > W - PAD_R) continue;
    ctx.beginPath();
    ctx.moveTo(x + 0.5, AXIS_H);
    ctx.lineTo(x + 0.5, H);
    ctx.stroke();
    ctx.fillText(formatMs(t), x, AXIS_H - 6);
  }}

  // Invocations
  qdata.invocations.forEach(inv => {{
    const x0 = PAD_L + ((inv.start - start) / duration) * drawW;
    const x1 = PAD_L + ((inv.end - start) / duration) * drawW;
    const y = AXIS_H + inv.slot * rowH;
    const w = Math.max(x1 - x0, 1);

    if (x1 < PAD_L || x0 > W - PAD_R) return;

    // Compute per-bar alpha (group/node mode dims whole bars; phase mode keeps bars visible)
    const barDimmed =
      (selectedGroup !== null && inv.group !== selectedGroup) ||
      (selectedNode !== null && inv.node_id !== selectedNode);

    // Background bar
    ctx.globalAlpha = barDimmed ? 0.15 : 1;
    ctx.fillStyle = '#e8ebee';
    ctx.strokeStyle = '#001F3F';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.rect(x0, y + 1, w, rowH - 2);
    ctx.fill();
    ctx.stroke();

    // Phase segments
    PHASE_ORDER.forEach(key => {{
      const seg = inv.phases[key];
      if (!seg) return;
      const px0 = PAD_L + ((seg[0] - start) / duration) * drawW;
      const px1 = PAD_L + ((seg[1] - start) / duration) * drawW;
      const pw = Math.max(px1 - px0, 0.5);
      if (px1 < PAD_L || px0 > W - PAD_R) return;
      const m = PHASE_META[key];
      // Phase mode: selected segment pops at full opacity, others fade to near-invisible
      if (selectedPhase !== null) {{
        ctx.globalAlpha = (key === selectedPhase) ? 1 : 0.08;
      }} else {{
        ctx.globalAlpha = barDimmed ? 0.15 : 1;
      }}
      ctx.fillStyle = m.face;
      ctx.strokeStyle = m.edge;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.rect(px0, y + 1, pw, rowH - 2);
      ctx.fill();
      ctx.stroke();
    }});

    // Remote overlay
    if (inv.on_remote) {{
      ctx.fillStyle = `rgba(255,255,255,${{REMOTE_ALPHA}})`;
      ctx.fillRect(x0, y + 1, w, rowH - 2);
    }}

    ctx.globalAlpha = 1;
  }});

  // Axis border
  ctx.fillStyle = '#f8f8f8';
  ctx.fillRect(0, 0, W, AXIS_H);
  ctx.strokeStyle = '#ddd';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, AXIS_H + 0.5);
  ctx.lineTo(W, AXIS_H + 0.5);
  ctx.stroke();

  // Re-draw axis labels on top
  ctx.fillStyle = '#999';
  ctx.font = '10px SF Mono, Fira Code, monospace';
  ctx.textAlign = 'center';
  for (let t = tickStart; t < start + duration; t += step) {{
    const x = PAD_L + ((t - start) / duration) * drawW;
    if (x < PAD_L || x > W - PAD_R) continue;
    ctx.fillText(formatMs(t), x, AXIS_H - 6);
  }}
}}

function formatMs(ms) {{
  if (ms >= 10000) return (ms / 1000).toFixed(1) + 's';
  if (ms >= 1000)  return (ms / 1000).toFixed(2) + 's';
  return ms.toFixed(0) + 'ms';
}}

// ── Event handling ───────────────────────────────────────────────────────────
function attachEvents(canvas, qdata, traceIdx) {{
  // Remove old listeners by cloning (simpler than tracking)
  const nc = canvas.cloneNode(false);
  nc.id = canvas.id;
  canvas.parentNode.replaceChild(nc, canvas);
  const c = nc;
  c.getContext; // keep reference

  const cid = c.id;

  // Scroll behavior (attached to the whole section so it works over the label and
  // any empty space too, not just directly on the canvas):
  //   Shift+scroll (or horizontal scroll — macOS converts Shift+trackpad-scroll to
  //     deltaX and may strip shiftKey) → adjust row height
  //   Cmd/Ctrl+scroll → zoom the time axis around the cursor
  //   Plain scroll → let the .trace-section scroll vertically (no preventDefault)
  const section = c.parentElement;
  if (section._wheelHandler) section.removeEventListener('wheel', section._wheelHandler);
  const wheelHandler = e => {{
    const absX = Math.abs(e.deltaX), absY = Math.abs(e.deltaY);
    if (e.shiftKey || absX > absY) {{
      e.preventDefault();
      const delta = absX > absY ? e.deltaX : e.deltaY;
      setRowH(rowH * (delta > 0 ? 0.833 : 1.2));
    }} else if (e.metaKey || e.ctrlKey) {{
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left - PAD_L;
      const drawW = c.width - PAD_L - PAD_R;
      const ratio = mx / drawW;
      const pivotTime = sharedView.start + ratio * sharedView.duration;
      const factor = e.deltaY > 0 ? 1.2 : 0.833;
      sharedView.duration = Math.max(10, sharedView.duration * factor);
      sharedView.start = pivotTime - ratio * sharedView.duration;
      clampView();
      redrawAll();
    }}
    // else: plain vertical scroll — allow native scrolling of the trace section
  }};
  section.addEventListener('wheel', wheelHandler, {{ passive: false }});
  section._wheelHandler = wheelHandler;

  // Pan — delegate to global drag state
  c.addEventListener('mousedown', e => {{
    if (e.button !== 0) return;
    drag = {{ canvas: c, qdata, startX: e.clientX, startViewStart: sharedView.start }};
  }});

  // Hover tooltip
  const tooltip = document.getElementById('tooltip');
  c.addEventListener('mousemove', e => {{
    if (drag && e.buttons === 1) return;
    const inv = hitTest(c, qdata, e);
    if (inv) {{
      showTooltip(e, inv);
      c.style.cursor = 'pointer';
    }} else {{
      tooltip.style.display = 'none';
      c.style.cursor = 'crosshair';
    }}
  }});
  c.addEventListener('mouseleave', () => {{ tooltip.style.display = 'none'; }});

  // Click: select group (suppress if it was a drag)
  c.addEventListener('click', e => {{
    if (drag && Math.abs(e.clientX - drag.startX) > 4) return;
    const inv = hitTest(c, qdata, e);
    if (inv && inv.group !== null) {{
      const next = selectedGroup === inv.group ? null : inv.group;
      clearFilter();
      selectedGroup = next;
    }} else {{
      clearFilter();
    }}
    redrawAll();
  }});
}}

function hitTest(canvas, qdata, e) {{
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const drawW = canvas.width - PAD_L - PAD_R;

  const time = sharedView.start + ((mx - PAD_L) / drawW) * sharedView.duration;
  const slot = Math.floor((my - AXIS_H) / rowH);

  for (const inv of qdata.invocations) {{
    if (inv.slot === slot && time >= inv.start && time <= inv.end) {{
      return inv;
    }}
  }}
  return null;
}}

function showTooltip(e, inv) {{
  const tooltip = document.getElementById('tooltip');
  const dur = inv.end - inv.start;
  const idxSuffix = (inv.group_index !== null && inv.group_index !== undefined)
    ? ` <span style="color:#aaa;font-weight:normal">[${{inv.group_index}}-${{inv.child_index}}]</span>` : '';
  let html = `<div class="tt-title">${{inv.id}}${{idxSuffix}}</div>`;
  html += `<div class="tt-row"><span class="tt-label">start</span><span class="tt-val">${{inv.start.toFixed(2)}} ms</span></div>`;
  html += `<div class="tt-row"><span class="tt-label">duration</span><span class="tt-val">${{dur.toFixed(2)}} ms</span></div>`;
  if (inv.on_remote) html += `<div class="tt-row"><span class="tt-label">execution</span><span class="tt-val" style="color:#89b4fa">remote</span></div>`;
  if (inv.node_id !== null && inv.node_id !== undefined) html += `<div class="tt-row"><span class="tt-label">node</span><span class="tt-val">${{inv.node_id}}</span></div>`;
  if (inv.group !== null) html += `<div class="tt-row"><span class="tt-label">group</span><span class="tt-val" style="color:#6c7086">#${{inv.group}} &nbsp;<span style="color:#aaa;font-weight:normal">(${{inv.group_size}} invocations)</span></span></div>`;
  if (inv.items) html += `<div class="tt-row"><span class="tt-label">items</span><span class="tt-val">${{inv.items}}</span></div>`;
  const bs = fmtBytes(inv.input_size);
  if (bs) html += `<div class="tt-row"><span class="tt-label">input size</span><span class="tt-val">${{bs}}</span></div>`;
  html += `<hr class="tt-sep">`;
  PHASE_ORDER.forEach(key => {{
    const seg = inv.phases[key];
    if (!seg) return;
    const d = seg[1] - seg[0];
    if (d <= 0) return;
    const m = PHASE_META[key];
    html += `<div class="tt-phase-row">
      <div class="tt-dot" style="background:${{m.face}};border:1px solid ${{m.edge}}"></div>
      <span class="tt-label">${{m.label}}</span>
      <span class="tt-phase-dur">${{d.toFixed(2)}} ms</span>
    </div>`;
  }});
  tooltip.innerHTML = html;
  tooltip.style.display = 'block';

  const tx = Math.min(e.clientX + 16, window.innerWidth - 330);
  const ty = Math.min(e.clientY + 10, window.innerHeight - tooltip.offsetHeight - 10);
  tooltip.style.left = tx + 'px';
  tooltip.style.top = ty + 'px';
}}

function redrawAll() {{
  document.querySelectorAll('canvas').forEach(c => {{
    const m = c.id.match(/canvas-(\\d+)/);
    if (!m) return;
    const qdata = TRACES[parseInt(m[1])]?.queries[activeQuery]?.runs[activeRun];
    if (!qdata) return;
    drawCanvas(c, qdata);
  }});
}}

// Keyboard shortcuts
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{ clearFilter(); redrawAll(); }}
  if ((e.key === 'r' || e.key === 'R') && !e.metaKey && !e.ctrlKey) {{
    sharedView = {{ start: 0, duration: sharedMaxTime * 1.02 }};
    redrawAll();
  }}
}});

// Resize: re-sync canvas bitmap sizes to new CSS layout
window.addEventListener('resize', resizeCanvases);

// Initial render
buildRunDropdown();
renderMain();
</script>
</body>
</html>"""

    with open(output_path, "w") as f:
        f.write(html)

    print(f"Written: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate interactive HTML trace viewer")
    parser.add_argument("folders", nargs="+", metavar="FOLDER",
                        help="Trace folder(s) containing timestamps.txt")
    parser.add_argument("-o", "--output", default="trace_viewer.html",
                        help="Output HTML file (default: trace_viewer.html)")
    args = parser.parse_args()

    traces = []
    for folder in args.folders:
        print(f"Parsing {folder}...")
        queries = parse_folder(folder)
        traces.append((os.path.basename(folder.rstrip("/")), queries))
        total_invs = sum(len(r["invocations"]) for q in queries.values() for r in q["runs"])
        print(f"  {len(queries)} queries, {total_invs} total invocations")

    generate_html(traces, args.output)


if __name__ == "__main__":
    main()
