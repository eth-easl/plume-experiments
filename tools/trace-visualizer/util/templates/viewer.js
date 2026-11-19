const DATA = JSON.parse(document.getElementById('trace-data').textContent);
const TRACES = DATA.traces;
const QUERY_NAMES = DATA.queryNames;
const BARS = DATA.bars;

let rowH = 5;
const AXIS_H = 24;
const PAD_L = 8;
const PAD_R = 8;
const REMOTE_ALPHA = 0.08;

// Shared view state — all canvases for the same query are synced
let activeQuery = QUERY_NAMES[0];
let activeRun = 0;
let sharedMaxTime = queryMaxTime(activeQuery);
let sharedView = { start: 0, duration: sharedMaxTime * 1.02 };

let selectedGroup = null;
let selectedBar = null;
let selectedNode = null;

function runData(traceIdx) {
  return TRACES[traceIdx]?.queries[activeQuery]?.runs[activeRun];
}

function queryMaxTime(name) {
  return Math.max(1, ...TRACES.map(t => t.queries[name]?.runs[activeRun]?.max_time || 0));
}

function resetView() {
  sharedView = { start: 0, duration: sharedMaxTime * 1.02 };
}

function clampView() {
  sharedView.duration = Math.max(10, Math.min(sharedMaxTime * 1.02, sharedView.duration));
  sharedView.start = Math.max(0, sharedView.start);
  const maxStart = Math.max(0, sharedMaxTime - sharedView.duration);
  if (sharedView.start > maxStart) sharedView.start = maxStart;
}

function clearFilter() {
  selectedGroup = null;
  selectedBar = null;
  selectedNode = null;
  document.querySelectorAll('.legend-item').forEach(li => li.classList.remove('active'));
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

function fmtBytes(b) {
  if (!b) return null;
  if (b >= 1048576) return (b / 1048576).toFixed(2) + ' MB';
  if (b >= 1024)    return (b / 1024).toFixed(1) + ' KB';
  return b + ' B';
}

function formatMs(ms) {
  if (ms >= 10000) return (ms / 1000).toFixed(1) + 's';
  if (ms >= 1000)  return (ms / 1000).toFixed(2) + 's';
  return ms.toFixed(0) + 'ms';
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
const tabsEl = document.getElementById('tabs');
QUERY_NAMES.forEach(name => {
  const t = document.createElement('div');
  t.className = 'tab' + (name === activeQuery ? ' active' : '');
  t.textContent = name;
  t.addEventListener('click', () => setQuery(name));
  tabsEl.appendChild(t);
});

// ── Bar legend ───────────────────────────────────────────────────────────────
const legendEl = document.getElementById('legend');
BARS.forEach((bar, bi) => {
  const item = document.createElement('div');
  item.className = 'legend-item';
  const swatch = document.createElement('div');
  swatch.className = 'legend-swatch';
  swatch.style.background = bar.face;
  swatch.style.border = `1px solid ${bar.edge}`;
  item.append(swatch, bar.label);
  item.addEventListener('click', () => {
    const wasSelected = selectedBar === bi;
    clearFilter();
    if (!wasSelected) {
      selectedBar = bi;
      item.classList.add('active');
    }
    redrawAll();
  });
  legendEl.appendChild(item);
});

// ── Node legend (rebuilt per query) ─────────────────────────────────────────
function buildNodeLegend() {
  const nodeEl = document.getElementById('node-legend');
  nodeEl.innerHTML = '';
  const allInvs = TRACES.flatMap((_, ti) => runData(ti)?.invocations || []);
  const nodeIds = [...new Set(allInvs
    .map(inv => inv.node_id)
    .filter(id => id !== null && id !== undefined)
  )].sort((a, b) => a - b);
  if (nodeIds.length === 0) { nodeEl.style.display = 'none'; return; }
  nodeEl.style.display = 'flex';
  const lbl = document.createElement('span');
  lbl.id = 'node-legend-label';
  lbl.textContent = 'Nodes:';
  nodeEl.appendChild(lbl);
  nodeIds.forEach(nid => {
    const item = document.createElement('div');
    item.className = 'legend-item';
    item.textContent = `Node ${nid}`;
    item.addEventListener('click', () => {
      const wasSelected = selectedNode === nid;
      clearFilter();
      if (!wasSelected) {
        selectedNode = nid;
        item.classList.add('active');
      }
      redrawAll();
    });
    nodeEl.appendChild(item);
  });
}

// ── Vertical zoom (row height) ───────────────────────────────────────────────
function setRowH(newH) {
  const rounded = newH > rowH ? Math.ceil(newH) : Math.floor(newH);
  rowH = Math.max(2, Math.min(40, rounded));
  document.getElementById('rowh-val').textContent = rowH;
  document.getElementById('rowh-slider').value = rowH;
  resizeAndRedrawAll();
}

document.getElementById('rowh-slider').addEventListener('input', e => {
  setRowH(parseInt(e.target.value));
});

document.getElementById('fit-btn').addEventListener('click', () => {
  // rowH that makes all slots visible within each section's viewport height
  let minFitH = Infinity;
  document.querySelectorAll('.trace-section').forEach(sec => {
    const c = sec.querySelector('canvas');
    const qdata = c && runData(c.dataset.trace);
    if (!qdata) return;
    const viewportH = sec.clientHeight - (sec.querySelector('.trace-label')?.offsetHeight || 0);
    minFitH = Math.min(minFitH, (viewportH - AXIS_H) / qdata.num_slots);
  });
  if (isFinite(minFitH)) setRowH(minFitH);
});

function traceCanvases() {
  return document.querySelectorAll('.trace-section canvas');
}

function resizeAndRedrawAll() {
  traceCanvases().forEach(c => {
    const qdata = runData(c.dataset.trace);
    if (!qdata) return;
    c.height = qdata.num_slots * rowH + AXIS_H;
    drawCanvas(c, qdata);
  });
}

// On window resize, update canvas widths only (height is content-driven)
function resizeCanvases() {
  traceCanvases().forEach(c => {
    const newW = Math.floor(c.getBoundingClientRect().width);
    if (!newW) return;
    c.width = newW;
    const qdata = runData(c.dataset.trace);
    if (qdata) drawCanvas(c, qdata);
  });
}

function redrawAll() {
  traceCanvases().forEach(c => {
    const qdata = runData(c.dataset.trace);
    if (qdata) drawCanvas(c, qdata);
  });
}

// ── Global drag state (one handler, not per-canvas) ─────────────────────────
let drag = null; // { canvas, startX, startViewStart }

window.addEventListener('mousemove', e => {
  if (!drag || !(e.buttons & 1)) { drag = null; return; }
  const drawW = drag.canvas.width - PAD_L - PAD_R;
  const dx = e.clientX - drag.startX;
  sharedView.start = drag.startViewStart - (dx / drawW) * sharedView.duration;
  clampView();
  redrawAll();
});
window.addEventListener('mouseup', () => { drag = null; });

// ── Run dropdown ─────────────────────────────────────────────────────────────
function buildRunDropdown() {
  const wrap = document.getElementById('run-wrap');
  const sel = document.getElementById('run-select');
  const count = Math.max(...TRACES.map(t => t.queries[activeQuery]?.runs?.length || 0));
  sel.innerHTML = '';
  for (let i = 0; i < count; i++) {
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = `Run ${i + 1}`;
    sel.appendChild(opt);
  }
  sel.value = activeRun;
  wrap.style.display = count > 1 ? 'flex' : 'none';
}

document.getElementById('run-select').addEventListener('change', e => {
  activeRun = parseInt(e.target.value);
  sharedMaxTime = queryMaxTime(activeQuery);
  resetView();
  clearFilter();
  renderMain();
});

// ── Query switcher ───────────────────────────────────────────────────────────
function setQuery(name) {
  activeQuery = name;
  activeRun = 0;
  tabsEl.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', QUERY_NAMES[i] === name);
  });
  clearFilter();
  sharedMaxTime = queryMaxTime(name);
  resetView();
  buildRunDropdown();
  renderMain();
}

// ── Main render ──────────────────────────────────────────────────────────────
function renderMain() {
  const main = document.getElementById('main');
  const sections = [];
  TRACES.forEach((trace, ti) => {
    const qdata = runData(ti);
    if (!qdata || qdata.invocations.length === 0) return;
    sections.push({ trace, qdata, ti });
  });

  // Rebuild sections if the trace count changed, otherwise reuse them
  const existing = main.querySelectorAll('.trace-section');
  if (existing.length !== sections.length) {
    main.innerHTML = '';
    sections.forEach(({ trace, qdata, ti }) => {
      const sec = document.createElement('div');
      sec.className = 'trace-section';
      if (TRACES.length > 1) {
        const lbl = document.createElement('div');
        lbl.className = 'trace-label';
        lbl.textContent = trace.name;
        sec.appendChild(lbl);
      }
      const canvas = document.createElement('canvas');
      sec.appendChild(canvas);
      main.appendChild(sec);
      setupCanvas(canvas, qdata, ti);
    });
  } else {
    sections.forEach(({ qdata, ti }, si) => {
      setupCanvas(existing[si].querySelector('canvas'), qdata, ti);
    });
  }
  buildNodeLegend();
  // After DOM is updated, sync canvas bitmap sizes to their CSS-rendered sizes
  requestAnimationFrame(resizeCanvases);
}

function setupCanvas(canvas, qdata, traceIdx) {
  // Replace the canvas to drop listeners bound to the previous query/run
  const c = canvas.cloneNode(false);
  canvas.parentNode.replaceChild(c, canvas);
  c.dataset.trace = traceIdx;
  c.width = c.parentElement.clientWidth || window.innerWidth;
  c.height = qdata.num_slots * rowH + AXIS_H;
  attachEvents(c, qdata);
}

// ── Drawing ──────────────────────────────────────────────────────────────────
function timeTicks(start, duration, drawW) {
  const nTicks = Math.max(4, Math.floor(drawW / 80));
  const rawStep = duration / nTicks;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const step = [1, 2, 5, 10].map(s => s * magnitude).find(s => s >= rawStep) || rawStep;
  const ticks = [];
  for (let t = Math.ceil(start / step) * step; t < start + duration; t += step) ticks.push(t);
  return ticks;
}

function drawCanvas(canvas, qdata) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const drawW = W - PAD_L - PAD_R;
  const { start, duration } = sharedView;
  const toX = t => PAD_L + ((t - start) / duration) * drawW;
  const ticks = timeTicks(start, duration, drawW)
    .map(t => ({ t, x: toX(t) }))
    .filter(({ x }) => x >= PAD_L && x <= W - PAD_R);

  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, W, H);

  // Grid lines
  ctx.strokeStyle = '#e8e8e8';
  ctx.lineWidth = 1;
  ticks.forEach(({ x }) => {
    ctx.beginPath();
    ctx.moveTo(x + 0.5, AXIS_H);
    ctx.lineTo(x + 0.5, H);
    ctx.stroke();
  });

  // Invocations
  qdata.invocations.forEach(inv => {
    const x0 = toX(inv.start);
    const x1 = toX(inv.end);
    if (x1 < PAD_L || x0 > W - PAD_R) return;
    const y = AXIS_H + inv.slot * rowH;
    const w = Math.max(x1 - x0, 1);

    // Group/node filters dim whole bars; the bar filter keeps bars visible
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

    // Bar segments
    inv.phases.forEach((seg, bi) => {
      if (!seg) return;
      const px0 = toX(seg[0]);
      const px1 = toX(seg[1]);
      if (px1 < PAD_L || px0 > W - PAD_R) return;
      const bar = BARS[bi];
      // Bar filter: selected segment pops at full opacity, others fade to near-invisible
      if (selectedBar !== null) {
        ctx.globalAlpha = bi === selectedBar ? 1 : 0.08;
      } else {
        ctx.globalAlpha = barDimmed ? 0.15 : 1;
      }
      ctx.fillStyle = bar.face;
      ctx.strokeStyle = bar.edge;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.rect(px0, y + 1, Math.max(px1 - px0, 0.5), rowH - 2);
      ctx.fill();
      ctx.stroke();
    });

    // Remote overlay
    if (inv.on_remote) {
      ctx.fillStyle = `rgba(255,255,255,${REMOTE_ALPHA})`;
      ctx.fillRect(x0, y + 1, w, rowH - 2);
    }

    ctx.globalAlpha = 1;
  });

  // Axis, drawn last so bars never cover it
  ctx.fillStyle = '#f8f8f8';
  ctx.fillRect(0, 0, W, AXIS_H);
  ctx.strokeStyle = '#ddd';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, AXIS_H + 0.5);
  ctx.lineTo(W, AXIS_H + 0.5);
  ctx.stroke();

  ctx.fillStyle = '#999';
  ctx.font = '10px SF Mono, Fira Code, monospace';
  ctx.textAlign = 'center';
  ticks.forEach(({ t, x }) => ctx.fillText(formatMs(t), x, AXIS_H - 6));
}

// ── Event handling ───────────────────────────────────────────────────────────
function attachEvents(c, qdata) {
  // Scroll behavior (attached to the whole section so it works over the label and
  // any empty space too, not just directly on the canvas):
  //   Shift+scroll (or horizontal scroll — macOS converts Shift+trackpad-scroll to
  //     deltaX and may strip shiftKey) → adjust row height
  //   Cmd/Ctrl+scroll → zoom the time axis around the cursor
  //   Plain scroll → let the .trace-section scroll vertically (no preventDefault)
  const section = c.parentElement;
  if (section._wheelHandler) section.removeEventListener('wheel', section._wheelHandler);
  const wheelHandler = e => {
    const absX = Math.abs(e.deltaX), absY = Math.abs(e.deltaY);
    if (e.shiftKey || absX > absY) {
      e.preventDefault();
      const delta = absX > absY ? e.deltaX : e.deltaY;
      setRowH(rowH * (delta > 0 ? 0.833 : 1.2));
    } else if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      const rect = c.getBoundingClientRect();
      const drawW = c.width - PAD_L - PAD_R;
      const ratio = (e.clientX - rect.left - PAD_L) / drawW;
      const pivotTime = sharedView.start + ratio * sharedView.duration;
      sharedView.duration = Math.max(10, sharedView.duration * (e.deltaY > 0 ? 1.2 : 0.833));
      sharedView.start = pivotTime - ratio * sharedView.duration;
      clampView();
      redrawAll();
    }
  };
  section.addEventListener('wheel', wheelHandler, { passive: false });
  section._wheelHandler = wheelHandler;

  // Pan — delegate to global drag state
  c.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    drag = { canvas: c, startX: e.clientX, startViewStart: sharedView.start };
  });

  // Hover tooltip
  const tooltip = document.getElementById('tooltip');
  c.addEventListener('mousemove', e => {
    if (drag && e.buttons === 1) return;
    const inv = hitTest(c, qdata, e);
    if (inv) {
      showTooltip(e, inv);
      c.style.cursor = 'pointer';
    } else {
      tooltip.style.display = 'none';
      c.style.cursor = 'crosshair';
    }
  });
  c.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });

  // Click: select group (suppress if it was a drag)
  c.addEventListener('click', e => {
    if (drag && Math.abs(e.clientX - drag.startX) > 4) return;
    const inv = hitTest(c, qdata, e);
    const next = inv && inv.group !== null && selectedGroup !== inv.group ? inv.group : null;
    clearFilter();
    selectedGroup = next;
    redrawAll();
  });
}

function hitTest(canvas, qdata, e) {
  const rect = canvas.getBoundingClientRect();
  const drawW = canvas.width - PAD_L - PAD_R;
  const time = sharedView.start + ((e.clientX - rect.left - PAD_L) / drawW) * sharedView.duration;
  const slot = Math.floor((e.clientY - rect.top - AXIS_H) / rowH);
  return qdata.invocations.find(inv => inv.slot === slot && time >= inv.start && time <= inv.end) || null;
}

function showTooltip(e, inv) {
  const tooltip = document.getElementById('tooltip');
  const row = (label, val, style = '') =>
    `<div class="tt-row"><span class="tt-label">${label}</span><span class="tt-val"${style ? ` style="${style}"` : ''}>${val}</span></div>`;

  const idxSuffix = inv.group_index !== null ? ` <span class="tt-idx">[${inv.group_index}-${inv.child_index}]</span>` : '';
  let html = `<div class="tt-title">${escapeHtml(inv.id)}${idxSuffix}</div>`;
  html += row('start', `${inv.start.toFixed(2)} ms`);
  html += row('duration', `${(inv.end - inv.start).toFixed(2)} ms`);
  if (inv.on_remote) html += row('execution', 'remote', 'color:#89b4fa');
  if (inv.node_id !== null && inv.node_id !== undefined) html += row('node', inv.node_id);
  if (inv.group !== null) html += row('group', `#${inv.group} &nbsp;<span class="tt-idx">(${inv.group_size} invocations)</span>`, 'color:#6c7086');
  (inv.data || []).forEach(([items, size], i) => {
    if (!items && !size) return;
    const parts = [];
    if (items) parts.push(`${items} item${items === 1 ? '' : 's'}`);
    if (size) parts.push(fmtBytes(size));
    html += row(`data ${i}`, parts.join(', '));
  });
  html += `<hr class="tt-sep">`;
  inv.phases.forEach((seg, bi) => {
    if (!seg) return;
    const d = seg[1] - seg[0];
    if (d <= 0) return;
    const bar = BARS[bi];
    html += `<div class="tt-phase-row">
      <div class="tt-dot" style="background:${bar.face};border:1px solid ${bar.edge}"></div>
      <span class="tt-label">${escapeHtml(bar.label)}</span>
      <span class="tt-phase-dur">${d.toFixed(2)} ms</span>
    </div>`;
  });
  tooltip.innerHTML = html;
  tooltip.style.display = 'block';

  const tx = Math.min(e.clientX + 16, window.innerWidth - 330);
  const ty = Math.min(e.clientY + 10, window.innerHeight - tooltip.offsetHeight - 10);
  tooltip.style.left = tx + 'px';
  tooltip.style.top = ty + 'px';
}

// ── Keyboard shortcuts ───────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { clearFilter(); redrawAll(); }
  if ((e.key === 'r' || e.key === 'R') && !e.metaKey && !e.ctrlKey) {
    resetView();
    redrawAll();
  }
});

// Resize: re-sync canvas bitmap sizes to new CSS layout
window.addEventListener('resize', resizeCanvases);

// Initial render
buildRunDropdown();
renderMain();
