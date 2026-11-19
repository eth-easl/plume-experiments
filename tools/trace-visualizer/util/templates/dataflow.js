'use strict';

const DATA = JSON.parse(document.getElementById('dataflow-data').textContent);
const SVG_NS = 'http://www.w3.org/2000/svg';

const state = { q: 0, metric: 'size', scale: 'sqrt', showInputs: true, labels: true, pinned: null };
const view = { k: 1, tx: 0, ty: 0 };
let graph = null;  // current layout

// ── Formatting ───────────────────────────────────────────────────────────────

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function sig(v, digits = 3) {
  if (v === 0) return '0';
  const d = Math.max(0, digits - 1 - Math.floor(Math.log10(Math.abs(v))));
  return v.toFixed(Math.min(d, 2));
}
function fmtBytes(b) {
  if (b == null) return '–';
  if (b < 1024) return `${Math.round(b)} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let i = -1;
  do { b /= 1024; i++; } while (b >= 1024 && i < units.length - 1);
  return `${sig(b)} ${units[i]}`;
}
function fmtNum(n) {
  if (n == null) return '–';
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toLocaleString('en-US', { maximumFractionDigits: 1 });
}
function fmtMs(ms) {
  if (ms == null) return '–';
  if (ms < 1) return `${Math.round(ms * 1000)} µs`;
  if (ms < 1000) return `${sig(ms)} ms`;
  return `${sig(ms / 1000)} s`;
}
/** mean, followed by the min–max range over runs if it varies. */
function fmtStat(st, f, plain = false) {
  if (!st) return '–';
  const main = f(st.mean);
  if (st.n > 1 && st.min !== st.max) {
    return plain ? `${main} (${f(st.min)}–${f(st.max)})` : `${main}<span class="rng">${f(st.min)}–${f(st.max)}</span>`;
  }
  return main;
}
function fmtRange(r, f) {
  if (!r) return '–';
  return r[0] === r[1] ? f(r[0]) : `${f(r[0])} – ${f(r[1])} <span class="rng">Δ ${f(r[1] - r[0])}</span>`;
}

// ── Colors ───────────────────────────────────────────────────────────────────

const fnColors = new Map();
DATA.queries.forEach(q => q.apps.forEach(a => {
  if (!fnColors.has(a.fn)) fnColors.set(a.fn, `var(--series-${fnColors.size % 8 + 1})`);
}));
const distColor = d => ({ all: 'var(--dist-all)', each: 'var(--dist-each)', keyed: 'var(--dist-keyed)' }[d] || 'var(--dist-none)');

// ── Text measuring ───────────────────────────────────────────────────────────

const measureCtx = document.createElement('canvas').getContext('2d');
const FONT_FAMILY = getComputedStyle(document.body).fontFamily;
function textWidth(s, size = 12, weight = 400) {
  measureCtx.font = `${weight} ${size}px ${FONT_FAMILY}`;
  return measureCtx.measureText(s).width;
}

// ── Graph construction and layout ────────────────────────────────────────────

const GAP_X = 110;
const NODE_SEP = 16;
const DUMMY_SEP = 8;
const MARGIN = 40;

function keyOf(ref) { return (ref.kind === 'app' ? 'a' : ref.kind === 'in' ? 'i' : 'o') + ref.ref; }

function appSub(a) {
  const parts = [];
  if (a.outs.length) parts.push(a.outs.join(', '));
  if (a.inv) parts.push(`×${fmtNum(Math.round(a.inv.mean * 10) / 10)}`);
  if (a.lat) parts.push(fmtMs(a.lat.wall.mean));
  return parts.join(' · ');
}

function buildGraph(q) {
  const nodes = [], byKey = new Map();
  const add = n => { n.inEdges = []; n.outEdges = []; nodes.push(n); byKey.set(n.key, n); return n; };
  q.apps.forEach(a => add({ key: 'a' + a.idx, kind: 'app', app: a, order: a.idx * 10 }));
  if (state.showInputs) q.inputs.forEach(c => add({ key: 'i' + c.name, kind: 'in', input: c }));
  q.outputs.forEach(o => add({ key: 'o' + o.name, kind: 'out', output: o }));

  const edges = [];
  q.edges.forEach(e => {
    const s = byKey.get(keyOf(e.from)), t = byKey.get(keyOf(e.to));
    if (!s || !t) return;
    const ed = { e, s, t };
    edges.push(ed);
    s.outEdges.push(ed);
    t.inEdges.push(ed);
  });
  // Drop composition pills without any edge
  const used = nodes.filter(n => n.kind === 'app' || n.inEdges.length || n.outEdges.length);

  // Node sizes
  used.forEach(n => {
    if (n.kind === 'app') {
      const a = n.app;
      const title = `${a.fn}`;
      const w = Math.max(textWidth(title, 12, 600) + textWidth(` #${a.idx}`, 10.5), textWidth(appSub(a), 10.5));
      n.w = Math.max(130, Math.ceil(w) + 22);
      const ports = new Set(n.inEdges.map(ed => ed.e.param)).size;
      n.h = Math.max(46, ports * 17 + 12);
    } else {
      const label = n.kind === 'in' ? n.input.name : n.output.name;
      n.w = Math.ceil(textWidth(label, 10.5)) + 18;
      n.h = 20;
    }
  });

  layout(used, edges);
  return { nodes: used, edges, q };
}

function layout(nodes, edges) {
  const apps = nodes.filter(n => n.kind === 'app');
  const appEdges = edges.filter(ed => ed.s.kind === 'app' && ed.t.kind === 'app');

  // Break cycles (DFS back edges), then longest-path layering of the applications
  const status = new Map(), topo = [];
  const visit = n => {
    status.set(n, 1);
    for (const ed of n.outEdges) {
      if (ed.t.kind !== 'app') continue;
      if (status.get(ed.t) === 1) ed.back = true;
      else if (!status.get(ed.t)) visit(ed.t);
    }
    status.set(n, 2);
    topo.push(n);
  };
  apps.forEach(n => { if (!status.get(n)) visit(n); });
  topo.reverse();
  const base = nodes.some(n => n.kind === 'in') ? 1 : 0;
  topo.forEach(n => {
    n.layer = base;
    n.inEdges.forEach(ed => { if (ed.s.kind === 'app' && !ed.back) n.layer = Math.max(n.layer, ed.s.layer + 1); });
  });
  nodes.forEach(n => {
    if (n.kind === 'in') {
      n.layer = Math.max(0, Math.min(...n.outEdges.map(ed => ed.t.layer)) - 1);
      n.order = Math.min(...n.outEdges.map(ed => ed.t.order)) - 5;
    } else if (n.kind === 'out') {
      n.layer = Math.max(...n.inEdges.map(ed => ed.s.layer)) + 1;
      n.order = Math.max(...n.inEdges.map(ed => ed.s.order)) + 5;
    }
  });

  // Dummy nodes for edges spanning several layers
  const all = nodes.slice();
  edges.forEach(ed => {
    ed.chain = [ed.s];
    if (!ed.back) {
      for (let l = ed.s.layer + 1; l < ed.t.layer; l++) {
        const d = { kind: 'dummy', layer: l, w: 0, h: 2, order: ed.s.order + 1, edge: ed };
        all.push(d);
        ed.chain.push(d);
      }
    }
    ed.chain.push(ed.t);
  });
  all.forEach(n => { n.up = []; n.down = []; });
  edges.forEach(ed => {
    if (ed.back) return;
    for (let i = 0; i + 1 < ed.chain.length; i++) {
      ed.chain[i].down.push(ed.chain[i + 1]);
      ed.chain[i + 1].up.push(ed.chain[i]);
    }
  });

  const nLayers = Math.max(...all.map(n => n.layer)) + 1;
  const layers = Array.from({ length: nLayers }, () => []);
  all.forEach(n => layers[n.layer].push(n));
  layers.forEach(L => { L.sort((a, b) => a.order - b.order); L.forEach((n, i) => { n.pos = i; }); });

  // Crossing reduction: barycenter sweeps, keeping the best ordering
  const crossings = () => {
    let c = 0;
    for (let l = 0; l + 1 < nLayers; l++) {
      const links = [];
      layers[l].forEach(u => u.down.forEach(v => links.push([u.pos, v.pos])));
      for (let i = 0; i < links.length; i++)
        for (let j = i + 1; j < links.length; j++)
          if ((links[i][0] - links[j][0]) * (links[i][1] - links[j][1]) < 0) c++;
    }
    return c;
  };
  let best = crossings(), bestOrder = layers.map(L => L.slice());
  for (let it = 0; it < 24 && best > 0; it++) {
    const down = it % 2 === 0;
    for (let s = 0; s < nLayers; s++) {
      const l = down ? s : nLayers - 1 - s;
      layers[l].forEach(n => {
        const nb = down ? n.up : n.down;
        n.bc = nb.length ? nb.reduce((acc, m) => acc + m.pos, 0) / nb.length : n.pos;
      });
      layers[l].sort((a, b) => a.bc - b.bc || a.pos - b.pos);
      layers[l].forEach((n, i) => { n.pos = i; });
    }
    const c = crossings();
    if (c < best) { best = c; bestOrder = layers.map(L => L.slice()); }
  }
  bestOrder.forEach((L, l) => { layers[l] = L; L.forEach((n, i) => { n.pos = i; }); });

  // x: one column per layer
  const colW = layers.map(L => Math.max(0, ...L.map(n => n.w)));
  const colX = [];
  let x = MARGIN;
  for (let l = 0; l < nLayers; l++) { colX.push(x); x += colW[l] + GAP_X; }
  all.forEach(n => { n.x = colX[n.layer] + (colW[n.layer] - n.w) / 2; n.cx = colX[n.layer] + colW[n.layer] / 2; });

  // y: start stacked, then pull nodes towards their neighbors while keeping order and spacing
  const sep = (a, b) => a.h / 2 + b.h / 2 + (a.kind === 'dummy' && b.kind === 'dummy' ? DUMMY_SEP : NODE_SEP);
  layers.forEach(L => {
    let y = 0;
    L.forEach((n, i) => { if (i) y += sep(L[i - 1], n); n.y = y; });
  });
  const place = (L, desired) => {
    const a = desired.slice(), b = desired.slice();
    for (let i = 1; i < L.length; i++) a[i] = Math.max(a[i], a[i - 1] + sep(L[i - 1], L[i]));
    for (let i = L.length - 2; i >= 0; i--) b[i] = Math.min(b[i], b[i + 1] - sep(L[i], L[i + 1]));
    L.forEach((n, i) => { n.y = (a[i] + b[i]) / 2; });
  };
  for (let it = 0; it < 40; it++) {
    const down = it % 2 === 0;
    for (let s = 0; s < nLayers; s++) {
      const L = layers[down ? s : nLayers - 1 - s];
      const desired = L.map(n => {
        const nb = it < 30 ? (down ? n.up : n.down) : n.up.concat(n.down);
        const ref = nb.length ? nb : n.up.concat(n.down);
        return ref.length ? ref.reduce((acc, m) => acc + m.y, 0) / ref.length : n.y;
      });
      place(L, desired);
    }
  }
  const minY = Math.min(...all.map(n => n.y - n.h / 2));
  all.forEach(n => { n.y += MARGIN - minY; n.top = n.y - n.h / 2; });
  graphBounds.w = x - GAP_X + MARGIN;
  graphBounds.h = Math.max(...all.map(n => n.top + n.h)) + MARGIN;

  // Ports: one per input set (incoming) and per produced set (outgoing), ordered by neighbor position
  nodes.forEach(n => {
    const assign = (list, keyFn, neighborY, side) => {
      const groups = new Map();
      list.forEach(ed => {
        const k = keyFn(ed);
        if (!groups.has(k)) groups.set(k, []);
        groups.get(k).push(ed);
      });
      const ports = [...groups.entries()].map(([k, eds]) => ({
        k, eds, ny: eds.reduce((acc, ed) => acc + neighborY(ed), 0) / eds.length,
      }));
      ports.sort((a, b) => a.ny - b.ny);
      ports.forEach((p, i) => {
        const y = n.top + n.h * (i + 1) / (ports.length + 1);
        p.eds.forEach(ed => { ed[side] = y; });
      });
    };
    assign(n.inEdges, ed => ed.e.param ?? ed.e.set, ed => ed.chain[ed.chain.length - 2].y, 'ty');
    assign(n.outEdges, ed => ed.e.set, ed => ed.chain[1].y, 'sy');
  });
}
const graphBounds = { w: 0, h: 0 };

function edgePath(ed) {
  const pts = [[ed.s.x + ed.s.w, ed.sy]];
  ed.chain.slice(1, -1).forEach(d => pts.push([d.cx, d.y]));
  pts.push([ed.t.x, ed.ty]);
  if (ed.back) {
    const [p, q] = [pts[0], pts[1]];
    const lift = Math.min(p[1], q[1]) - 60;
    return `M${p[0]},${p[1]} C${p[0] + 120},${p[1]} ${p[0] + 120},${lift} ${(p[0] + q[0]) / 2},${lift} ` +
           `S${q[0] - 120},${q[1]} ${q[0]},${q[1]}`;
  }
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [px, py] = pts[i - 1], [qx, qy] = pts[i];
    const dx = Math.max(20, (qx - px) / 2);
    d += ` C${px + dx},${py} ${qx - dx},${qy} ${qx},${qy}`;
  }
  return d;
}

// ── Rendering ────────────────────────────────────────────────────────────────

const MIN_W = 1.5, MAX_W = 18;

function edgeValue(e) {
  const st = state.metric === 'size' ? e.size : e.items;
  return st ? st.mean : null;
}

function widthScale(edges) {
  const vals = edges.map(ed => edgeValue(ed.e)).filter(v => v > 0);
  if (!vals.length) return () => MIN_W;
  const max = Math.max(...vals), min = Math.min(...vals);
  const f = state.scale === 'log' ? v => Math.log1p(v / min) : state.scale === 'sqrt' ? Math.sqrt : v => v;
  return v => (v > 0 ? MIN_W + (MAX_W - MIN_W) * f(v) / f(max) : 1.25);
}

function el(tag, attrs = {}, parent = null) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function render() {
  const q = DATA.queries[state.q];
  graph = buildGraph(q);
  const vp = document.getElementById('viewport');
  vp.replaceChildren();
  const width = widthScale(graph.edges);
  const qLat = q.traceLatency ? q.traceLatency.mean : null;

  const gEdges = el('g', {}, vp), gLabels = el('g', {}, vp), gNodes = el('g', {}, vp);
  graph.edges.forEach(ed => { ed.w = width(edgeValue(ed.e)); });
  graph.edges.slice().sort((a, b) => b.w - a.w).forEach(ed => {
    const v = edgeValue(ed.e);
    const g = el('g', { class: 'edge' + (v > 0 ? '' : ' zero') }, gEdges);
    const d = edgePath(ed);
    el('path', { d, class: 'vis', style: `stroke:${distColor(ed.e.dist)};stroke-width:${ed.w}` }, g);
    el('path', { d, class: 'hit', 'stroke-width': Math.max(ed.w, 10) }, g);
    ed.g = g;
    g.addEventListener('mouseenter', ev => hover({ edge: ed }, ev));
    g.addEventListener('mousemove', moveTooltip);
    g.addEventListener('mouseleave', () => hover(null));
    g.addEventListener('click', ev => { ev.stopPropagation(); pin({ edge: ed }, ev); });
  });

  if (state.labels) {
    const seen = new Set();
    graph.edges.forEach(ed => {
      if (ed.t.kind !== 'app' || !ed.e.param) return;
      const k = `${ed.t.key}/${ed.e.param}`;
      const t = el('text', { x: ed.t.x - 5, y: ed.ty - Math.max(3, ed.w / 2 + 2), 'text-anchor': 'end', class: 'edge-label' }, gLabels);
      t.textContent = seen.has(k) ? '' : ed.e.param;
      seen.add(k);
      ed.label = t;
    });
  }

  graph.nodes.forEach(n => {
    const g = el('g', { class: `node ${n.kind}`, transform: `translate(${n.x},${n.top})` }, gNodes);
    n.g = g;
    if (n.kind === 'app') {
      const a = n.app, color = fnColors.get(a.fn);
      el('rect', { class: 'box', width: n.w, height: n.h, rx: 6 }, g);
      el('rect', { x: 0, y: 0, width: 4, height: n.h, rx: 2, style: `fill:${color}` }, g);
      const t = el('text', { x: 12, y: n.h / 2 - 3, 'font-size': 12, 'font-weight': 600 }, g);
      t.textContent = a.fn;
      const idx = el('tspan', { class: 'sub', 'font-weight': 400, dx: 6, style: 'fill:var(--text-muted);font-size:10.5px' }, t);
      idx.textContent = `#${a.idx}`;
      const sub = el('text', { x: 12, y: n.h / 2 + 12, class: 'sub' }, g);
      sub.textContent = appSub(a);
      if (a.lat && qLat) {  // when the application was active, relative to the query's latency
        const x0 = 12, w = n.w - 20, y = n.h - 6;
        el('rect', { class: 'track', x: x0, y, width: w, height: 3, rx: 1.5 }, g);
        const s = Math.min(1, a.lat.start.mean / qLat), e = Math.min(1, a.lat.end.mean / qLat);
        el('rect', { x: x0 + w * s, y, width: Math.max(2, w * (e - s)), height: 3, rx: 1.5, style: `fill:${color}` }, g);
      }
    } else {
      el('rect', { class: 'box', width: n.w, height: n.h, rx: 10 }, g);
      const t = el('text', { x: n.w / 2, y: n.h / 2 + 4, 'text-anchor': 'middle', class: 'pill' }, g);
      t.textContent = n.kind === 'in' ? n.input.name : n.output.name;
    }
    g.addEventListener('mouseenter', ev => hover({ node: n }, ev));
    g.addEventListener('mousemove', moveTooltip);
    g.addEventListener('mouseleave', () => hover(null));
    g.addEventListener('click', ev => { ev.stopPropagation(); pin({ node: n }, ev); });
  });

  renderHeader(q);
}

function renderHeader(q) {
  const stat = (label, value, sub = '') =>
    `<div class="stat"><span class="stat-label">${label}</span><span class="stat-value">${value}` +
    `${sub ? ` <span class="stat-sub">${sub}</span>` : ''}</span></div>`;
  const rng = st => (st && st.n > 1 ? `${fmtMs(st.min)}–${fmtMs(st.max)} · ${st.n} runs` : st ? '1 run' : '');
  const parts = [];
  if (q.latency) parts.push(stat('Query latency (mean)', fmtMs(q.latency.mean), rng(q.latency)));
  if (q.traceLatency) parts.push(stat(q.latency ? 'Traced latency' : 'Query latency (traced, mean)',
                                      fmtMs(q.traceLatency.mean), rng(q.traceLatency)));
  parts.push(stat('Function applications', q.apps.length));
  const inv = q.apps.reduce((acc, a) => acc + (a.inv ? a.inv.mean : 0), 0);
  parts.push(stat('Invocations', fmtNum(Math.round(inv * 10) / 10)));
  const moved = q.edges.reduce((acc, e) => acc + (e.size ? e.size.mean : 0), 0);
  parts.push(stat('Data transferred', fmtBytes(moved), 'sum over edges'));
  if (q.composition == null) parts.push(stat('Composition', 'missing'));
  document.getElementById('stats').innerHTML = parts.join('');

  const notes = DATA.warnings.filter(w => w.startsWith(q.name + ':')).map(w => w.slice(q.name.length + 1).trim());
  if (q.nDataRuns === 0) notes.unshift('no run of this query contains data entries');
  document.getElementById('notes').textContent = notes.length ? '⚠ ' + notes.join(' · ') : '';
}

function renderLegend() {
  const items = [['all', 'all'], ['each', 'each'], ['keyed', 'keyed'], [null, 'other / output']]
    .map(([d, label]) => `<span class="legend-item"><span class="legend-line" style="border-color:${distColor(d)}"></span>${label}</span>`);
  items.push('<span class="legend-item"><span class="legend-line dashed"></span>no data recorded</span>');
  document.getElementById('legend').innerHTML = items.join('');
}

// ── Tooltips ─────────────────────────────────────────────────────────────────

const tooltip = document.getElementById('tooltip');

function appName(a) { return `#${a.idx} ${a.fn}`; }
function nodeName(n) {
  return n.kind === 'app' ? appName(n.app) : n.kind === 'in' ? `input ${n.input.name}` : `output ${n.output.name}`;
}

function nodeTooltip(n) {
  const q = DATA.queries[state.q];
  if (n.kind !== 'app') {
    const isIn = n.kind === 'in';
    const name = isIn ? n.input.name : n.output.name;
    const eds = isIn ? n.outEdges : n.inEdges;
    let h = `<div class="tt-title">Composition ${isIn ? 'input' : 'output'} ${esc(name)}</div>`;
    h += `<div class="tt-sub">${isIn ? 'consumed by' : 'produced by'} ${eds.map(ed => esc(nodeName(isIn ? ed.t : ed.s))).join(', ')}</div>`;
    if (isIn && n.input.undefined) h += '<div class="tt-note">This set is neither a composition input nor produced by a statement.</div>';
    if (isIn && n.input.size && n.input.size.mean > 0) {
      h += `<table><tr><td class="k">Recorded at composition</td><td>${fmtStat(n.input.items, fmtNum)} items · ${fmtStat(n.input.size, fmtBytes)}</td></tr></table>`;
    }
    return h;
  }
  const a = n.app;
  let h = `<div class="tt-title"><span class="sw" style="background:${fnColors.get(a.fn)}"></span>${esc(appName(a))}` +
          `${a.outs.length ? ` → ${esc(a.outs.join(', '))}` : ''}<span class="tt-pin">${state.pinned ? 'pinned · Esc to close' : 'click to pin'}</span></div>`;
  h += `<div class="tt-sub">${a.by ? 'by ' + esc(a.by) : 'statement ' + a.idx + ' of ' + esc(q.composition || q.name)}</div>`;

  const nodes = a.nodes.count;
  const ids = a.nodes.ids.length <= 12 ? a.nodes.ids.join(', ') : `${a.nodes.ids.slice(0, 12).join(', ')}, …`;
  h += '<table>';
  h += `<tr><td class="k">Invocations</td><td>${fmtStat(a.inv, fmtNum)}</td></tr>`;
  h += `<tr><td class="k">Parallelized over</td><td>${nodes ? fmtStat(nodes, fmtNum) : '–'} node${nodes && nodes.mean === 1 ? '' : 's'}` +
       `${a.nodes.ids.length ? ` <span class="muted">(node id${a.nodes.ids.length > 1 ? 's' : ''} ${ids})</span>` : ''}</td></tr>`;
  if (a.lat) {
    h += `<tr><td class="k">Execution latency</td><td>${fmtStat(a.lat.wall, fmtMs)} <span class="muted">wall clock, ` +
         `${fmtMs(a.lat.start.mean)} → ${fmtMs(a.lat.end.mean)} after query start</span></td></tr>`;
    h += `<tr><td class="k">Per invocation</td><td>mean ${fmtMs(a.lat.inv.mean)} <span class="muted">(min ${fmtMs(a.lat.inv.min)}, max ${fmtMs(a.lat.inv.max)})</span></td></tr>`;
  } else {
    h += '<tr><td class="k">Execution latency</td><td class="muted">no timestamps</td></tr>';
  }
  if (a.mem) {
    const m = a.mem;
    const partial = m.recorded < m.invocations ? ` <span class="muted">(recorded for ${fmtNum(m.recorded)} of ${fmtNum(m.invocations)} invocations)</span>` : '';
    h += `<tr><td class="k">Max memory</td><td>${fmtStat(m.peak, fmtBytes)} <span class="muted">largest invocation</span>${partial}</td></tr>`;
    h += `<tr><td class="k">Per invocation</td><td>mean ${fmtBytes(m.inv.mean)} <span class="muted">(min ${fmtBytes(m.inv.min)}, max ${fmtBytes(m.inv.max)})</span></td></tr>`;
    h += `<tr><td class="k">Sum over invocations</td><td>${fmtStat(m.sum, fmtBytes)}</td></tr>`;
  } else {
    h += '<tr><td class="k">Max memory</td><td class="muted">not recorded</td></tr>';
  }
  h += '</table>';

  // Data sets
  h += '<div class="tt-section">Data sets <span style="text-transform:none">(totals: mean over runs, per invocation: least – most)</span></div>';
  h += '<table><tr><th>set</th><th>bound to</th><th class="num">items</th><th class="num">size</th>' +
       '<th class="num">items / invocation</th><th class="num">size / invocation</th></tr>';
  let prevKind = null;
  a.sets.forEach(s => {
    const cls = prevKind && prevKind !== s.kind ? ' class="sep"' : '';
    prevKind = s.kind;
    const label = `<span class="muted">${s.kind === 'in' ? 'in' : 'out'}</span> ${esc(s.name)}`;
    const binding = s.binding ? esc(s.binding) : '<span class="muted">unbound</span>';
    if (s.traced) {
      h += `<tr${cls}><td>${label}</td><td>${binding}</td><td class="num">${fmtStat(s.items, fmtNum)}</td>` +
           `<td class="num">${fmtStat(s.size, fmtBytes)}</td><td class="num">${fmtRange(s.invItems, fmtNum)}</td>` +
           `<td class="num">${fmtRange(s.invSize, fmtBytes)}</td></tr>`;
    } else if (s.estimate) {
      h += `<tr${cls}><td>${label}</td><td>${binding}</td><td class="num est" title="estimated from ${esc(s.estimate)}">≈ ${fmtStat(s.items, fmtNum)}</td>` +
           `<td class="num est" title="estimated from ${esc(s.estimate)}">≈ ${fmtStat(s.size, fmtBytes)}</td>` +
           `<td class="num muted" colspan="2">not traced</td></tr>`;
    } else {
      h += `<tr${cls}><td>${label}</td><td>${binding}</td><td class="num muted" colspan="4">not traced</td></tr>`;
    }
  });
  h += '</table>';
  if (a.sets.some(s => s.estimate)) {
    h += '<div class="tt-note"><span class="est">≈</span> output sets are not traced; estimated from what their consumers received ' +
         '(hover the value for the consumer used).</div>';
  }

  // Latency phases
  if (a.lat && a.lat.phases.length) {
    const total = a.lat.phases.reduce((acc, p) => acc + p.mean, 0) || 1;
    h += '<div class="tt-section">Mean phase durations per invocation</div><div class="phase-bar">' +
         a.lat.phases.map(p => `<span style="width:${100 * p.mean / total}%;background:${p.color}" title="${esc(p.label)}"></span>`).join('') +
         '</div><table><tr><th></th><th>phase</th><th class="num">mean</th><th class="num">max</th><th class="num">sum / run</th></tr>' +
         a.lat.phases.map(p => `<tr><td><span class="sw" style="background:${p.color}"></span></td><td>${esc(p.label)}</td>` +
                               `<td class="num">${fmtMs(p.mean)}</td><td class="num">${fmtMs(p.max)}</td><td class="num">${fmtMs(p.total)}</td></tr>`).join('') +
         '</table>';
  }
  return h;
}

function edgeTooltip(ed) {
  const e = ed.e;
  const target = ed.t.kind === 'app' ? `${esc(appName(ed.t.app))} · <b>${esc(e.param)}</b>` : `composition output ${esc(e.set)}`;
  let h = `<div class="tt-title"><span class="sw" style="background:${distColor(e.dist)}"></span>${esc(e.set)} → ${target}` +
          `<span class="tt-pin">${state.pinned ? 'pinned · Esc to close' : 'click to pin'}</span></div>`;
  h += `<div class="tt-sub">from ${esc(nodeName(ed.s))}${e.dist ? ` · distribution <b>${esc(e.dist)}</b>` : ''}</div>`;
  if (!e.traced || !e.size) {
    h += '<div class="tt-note">No data recorded for this edge (the composition outputs are not part of the trace).</div>';
    return h;
  }
  const q = DATA.queries[state.q];
  h += '<table>';
  h += `<tr><td class="k">Size</td><td>${fmtStat(e.size, fmtBytes)}${e.size.n > 1 ? ` <span class="muted">mean over ${e.size.n} runs</span>` : ''}</td></tr>`;
  h += `<tr><td class="k">Items</td><td>${fmtStat(e.items, fmtNum)}</td></tr>`;
  if (e.size.n > 1) {
    h += `<tr><td class="k">min / max</td><td>${fmtBytes(e.size.min)} / ${fmtBytes(e.size.max)} · ${fmtNum(e.items.min)} / ${fmtNum(e.items.max)} items</td></tr>`;
  }
  if (ed.t.kind === 'app') {
    h += `<tr><td class="k">Per invocation</td><td>${fmtRange(e.invItems, fmtNum)} items · ${fmtRange(e.invSize, fmtBytes)}</td></tr>`;
  }
  h += '</table>';
  if (e.size.mean === 0 && e.items.mean === 0) {
    h += '<div class="tt-note">Recorded as 0 items / 0 B; this input set is likely not traced.</div>';
  }
  if (e.shared > 1) {
    h += `<div class="tt-note">${esc(e.param)} is fed by ${e.shared} sets; the values are for the combined input set.</div>`;
  }
  if (e.dist === 'all' && ed.t.kind === 'app') {
    h += '<div class="tt-note">Distribution <b>all</b>: every invocation receives the whole set, so the total counts it once per invocation.</div>';
  }
  return h;
}

function showTooltip(target, ev) {
  tooltip.innerHTML = target.node ? nodeTooltip(target.node) : edgeTooltip(target.edge);
  tooltip.style.display = 'block';
  moveTooltip(ev);
}

function moveTooltip(ev) {
  if (state.pinned || !ev || tooltip.style.display !== 'block') return;
  const pad = 14, r = tooltip.getBoundingClientRect();
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + r.width > window.innerWidth - 8) x = Math.max(8, ev.clientX - r.width - pad);
  if (y + r.height > window.innerHeight - 8) y = Math.max(8, window.innerHeight - r.height - 8);
  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;
}

function highlight(target) {
  const svg = document.getElementById('graph');
  if (!graph) return;
  graph.nodes.forEach(n => n.g.classList.remove('hl'));
  graph.edges.forEach(ed => { ed.g.classList.remove('hl'); if (ed.label) ed.label.classList.remove('hl'); });
  if (!target) { svg.classList.remove('dim'); return; }
  svg.classList.add('dim');
  const mark = ed => { ed.g.classList.add('hl'); if (ed.label) ed.label.classList.add('hl'); ed.s.g.classList.add('hl'); ed.t.g.classList.add('hl'); };
  if (target.node) {
    target.node.g.classList.add('hl');
    target.node.inEdges.concat(target.node.outEdges).forEach(mark);
  } else {
    mark(target.edge);
  }
}

function hover(target, ev) {
  if (state.pinned) return;
  highlight(target);
  if (target) showTooltip(target, ev);
  else tooltip.style.display = 'none';
}

function pin(target, ev) {
  state.pinned = null;
  highlight(target);
  showTooltip(target, ev);
  state.pinned = target;
  tooltip.classList.add('pinned');
  tooltip.innerHTML = target.node ? nodeTooltip(target.node) : edgeTooltip(target.edge);
}

function unpin() {
  state.pinned = null;
  tooltip.classList.remove('pinned');
  tooltip.style.display = 'none';
  highlight(null);
}

// ── Pan / zoom ───────────────────────────────────────────────────────────────

const canvas = document.getElementById('canvas');

function applyView() {
  document.getElementById('viewport').setAttribute('transform', `translate(${view.tx},${view.ty}) scale(${view.k})`);
}

function fit() {
  const r = canvas.getBoundingClientRect();
  const k = Math.min(1.4, r.width / graphBounds.w, r.height / graphBounds.h);
  view.k = k;
  view.tx = (r.width - graphBounds.w * k) / 2;
  view.ty = (r.height - graphBounds.h * k) / 2;
  applyView();
}

canvas.addEventListener('wheel', ev => {
  ev.preventDefault();
  const r = canvas.getBoundingClientRect();
  const mx = ev.clientX - r.left, my = ev.clientY - r.top;
  const factor = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015));
  const k = Math.min(6, Math.max(0.1, view.k * factor));
  view.tx = mx - (mx - view.tx) * k / view.k;
  view.ty = my - (my - view.ty) * k / view.k;
  view.k = k;
  applyView();
}, { passive: false });

let drag = null;
canvas.addEventListener('mousedown', ev => {
  if (ev.button !== 0) return;
  drag = { x: ev.clientX, y: ev.clientY, tx: view.tx, ty: view.ty, moved: false };
  canvas.classList.add('panning');
});
window.addEventListener('mousemove', ev => {
  if (!drag) return;
  const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
  if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
  view.tx = drag.tx + dx;
  view.ty = drag.ty + dy;
  applyView();
});
window.addEventListener('mouseup', () => { canvas.classList.remove('panning'); setTimeout(() => { drag = null; }, 0); });
canvas.addEventListener('click', () => { if (!drag || !drag.moved) unpin(); });
window.addEventListener('keydown', ev => { if (ev.key === 'Escape') unpin(); });
window.addEventListener('resize', fit);

// ── Controls ─────────────────────────────────────────────────────────────────

function seg(id, key) {
  const box = document.getElementById(id);
  box.addEventListener('click', ev => {
    const b = ev.target.closest('button');
    if (!b) return;
    state[key] = b.dataset.v;
    box.querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
    unpin();
    render();
  });
}

function selectQuery(i) {
  state.q = i;
  document.getElementById('query').value = String(i);
  try { history.replaceState(null, '', '#' + encodeURIComponent(DATA.queries[i].name)); } catch (e) { /* file:// */ }
  unpin();
  render();
  fit();
}

function init() {
  const sel = document.getElementById('query');
  if (!DATA.queries.length) {
    document.getElementById('stats').textContent = 'The trace contains no queries.';
    return;
  }
  DATA.queries.forEach((q, i) => {
    const o = document.createElement('option');
    o.value = String(i);
    o.textContent = q.latency ? `${q.name}  (${fmtMs(q.latency.mean)})` : q.name;
    sel.appendChild(o);
  });
  sel.addEventListener('change', () => selectQuery(Number(sel.value)));
  seg('metric', 'metric');
  seg('scale', 'scale');
  document.getElementById('show-inputs').addEventListener('change', ev => { state.showInputs = ev.target.checked; unpin(); render(); fit(); });
  document.getElementById('show-labels').addEventListener('change', ev => { state.labels = ev.target.checked; unpin(); render(); });
  document.getElementById('fit-btn').addEventListener('click', fit);
  renderLegend();

  const fromHash = DATA.queries.findIndex(q => '#' + encodeURIComponent(q.name) === location.hash);
  selectQuery(Math.max(0, fromHash));
}

init();
