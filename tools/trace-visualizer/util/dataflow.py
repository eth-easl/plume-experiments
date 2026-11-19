"""Aggregates traces per function application for the dataflow graph viewer.

Mapping between a trace and its composition (`.ddsl`):

- A query's runs are matched to the composition of the same name.
- The child group `g` of the root invocation (`Composition`) holds the invocations of the
  composition's statement `g` (its function application).
- The data entries of an invocation are its input sets, in the order of the function's
  parameters. Entries beyond the parameters (if the tracer reports them) are taken as the
  output sets, in the order of the function's outputs. The same holds for the root
  invocation and the composition's inputs/outputs.

The data transferred over an edge (set S -> input set P of application A) is the sum of
entry P over all invocations of A, i.e. what was actually delivered (an `all` input is
counted once per invocation). Output sets that are not traced are estimated from their
consumers: the sum over the consumer's invocations for `each`/`keyed`, the largest
per-invocation value for `all`.

Statistics over runs are reported as {mean, min, max}. Per-invocation spreads (the
invocation with the least/most items or bytes) are pooled over all runs.
"""

import json
import re
from dataclasses import replace
from html import escape
from pathlib import Path

from .config import Config
from .ddsl import Composition, Function, Program
from .layout import _resolve
from .model import Invocation, Run, Trace

TEMPLATE_DIR = Path(__file__).parent / "templates"
US_PER_MS = 1000


def _natural_key(name: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def _stat(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"mean": sum(values) / len(values), "min": min(values), "max": max(values), "n": len(values)}


def read_timings(path: str) -> dict[str, list[float]]:
    """Parses `Query <name>: <v>,<v>,...` lines (one value per run, in ms)."""
    timings: dict[str, list[float]] = {}
    with open(path) as f:
        for line in f:
            m = re.match(r"\s*Query\s+(\S+?)\s*:\s*(.*)", line)
            if not m:
                continue
            values = [float(v) for v in re.split(r"[,\s;]+", m.group(2).strip()) if v]
            timings.setdefault(m.group(1), []).extend(values)
    return timings


# ── Per-run extraction ───────────────────────────────────────────────────────

def _root_and_groups(run: Run) -> tuple[Invocation | None, dict[int, list[Invocation]]]:
    """The run's root invocation and its direct children, by child group index."""
    root_idx = next((i for i, inv in enumerate(run.invocations) if inv.parent is None), None)
    groups: dict[int, list[Invocation]] = {}
    if root_idx is None:
        return None, groups
    for inv in run.invocations:
        if inv.parent == root_idx:
            groups.setdefault(inv.group, []).append(inv)
    return run.invocations[root_idx], groups


def _entry(inv: Invocation, k: int) -> tuple[int, int]:
    if inv.data is None or k >= len(inv.data):
        return 0, 0
    d = inv.data[k]
    return d.items, d.size


class _SetAgg:
    """Collects one data entry index over the invocations of one application, across runs."""

    def __init__(self):
        self.tot_items: list[int] = []  # per run
        self.tot_size: list[int] = []
        self.max_items: list[int] = []  # per run: largest per-invocation value
        self.max_size: list[int] = []
        self.inv_items: list[int] = []  # pooled over runs
        self.inv_size: list[int] = []

    def add_run(self, invs: list[Invocation], k: int) -> None:
        entries = [_entry(inv, k) for inv in invs]
        items = [e[0] for e in entries]
        sizes = [e[1] for e in entries]
        self.tot_items.append(sum(items))
        self.tot_size.append(sum(sizes))
        self.max_items.append(max(items, default=0))
        self.max_size.append(max(sizes, default=0))
        self.inv_items += items
        self.inv_size += sizes

    def totals(self) -> dict:
        return {"items": _stat(self.tot_items), "size": _stat(self.tot_size)}

    def per_inv_max(self) -> dict:
        return {"items": _stat(self.max_items), "size": _stat(self.max_size)}

    def to_json(self) -> dict:
        return {
            **self.totals(),
            "invItems": [min(self.inv_items), max(self.inv_items)] if self.inv_items else None,
            "invSize": [min(self.inv_size), max(self.inv_size)] if self.inv_size else None,
        }


def _latency(runs_invs: list[list[Invocation]], ts_names: list[str], cfg: Config) -> dict | None:
    """Wall-clock window, per-invocation span and phase durations of one application (ms)."""
    index = {n: i for i, n in enumerate(ts_names)}
    # References to timestamps the trace does not have are treated as unset
    known = lambda refs: [r for r in refs if not isinstance(r, str) or r in index]
    cfg = Config(bars=[replace(b, start=known(b.start), end=known(b.end)) for b in cfg.bars],
                 span_start=known(cfg.span_start), span_end=known(cfg.span_end), remote=cfg.remote)
    walls, starts, ends, spans = [], [], [], []
    phases = [[] for _ in cfg.bars]
    for invs in runs_invs:
        run_start, run_end = None, None
        for inv in invs:
            if inv.ts is None:
                continue
            bars = []
            for bi, bar in enumerate(cfg.bars):
                s, e = _resolve(bar.start, inv.ts, index), _resolve(bar.end, inv.ts, index)
                if s is not None and e is not None:
                    phases[bi].append(max(0.0, e - s))
                    bars.append((min(s, e), e))
            s = _resolve(cfg.span_start, inv.ts, index) if cfg.span_start else None
            e = _resolve(cfg.span_end, inv.ts, index) if cfg.span_end else None
            if s is None:
                s = min((b[0] for b in bars), default=None)
            if e is None:
                e = max((b[1] for b in bars), default=None)
            if s is None or e is None:
                continue
            e = max(s, e)
            spans.append(e - s)
            run_start = s if run_start is None else min(run_start, s)
            run_end = e if run_end is None else max(run_end, e)
        if run_start is not None:
            starts.append(run_start)
            ends.append(run_end)
            walls.append(run_end - run_start)
    if not walls:
        return None
    return {
        "wall": _stat(walls), "start": _stat(starts), "end": _stat(ends), "inv": _stat(spans),
        "phases": [{"label": bar.label, "color": bar.face, "mean": sum(v) / len(v), "max": max(v),
                    "total": sum(v) / len(walls)}
                   for bar, v in zip(cfg.bars, phases) if v],
    }


def _memory(runs_invs: list[list[Invocation]]) -> dict | None:
    """Maximum memory of the invocations of one application (bytes), ignoring unrecorded (0) values.

    `runs_invs` holds the invocations of the runs with memory information only.
    """
    per_inv, peaks, sums = [], [], []
    n_invs = 0
    for invs in runs_invs:
        n_invs += len(invs)
        values = [inv.max_mem for inv in invs if inv.max_mem]
        if values:
            per_inv += values
            peaks.append(max(values))
            sums.append(sum(values))
    if not per_inv:
        return None
    return {"inv": _stat(per_inv), "peak": _stat(peaks), "sum": _stat(sums),
            "recorded": len(per_inv), "invocations": n_invs}


def _root_latency(run: Run) -> float | None:
    root, _ = _root_and_groups(run)
    if root is None or root.ts is None:
        return None
    return max(root.ts) / US_PER_MS


# ── Query assembly ───────────────────────────────────────────────────────────

def _function_for(prog: Program, name: str, n_entries: int) -> Function:
    fn = prog.functions.get(name)
    if fn is None:  # unknown signature: number the entries
        fn = Function(name, [f"d{k}" for k in range(n_entries)], [])
    return fn


def build_query(name: str, runs: list[Run], comp: Composition | None, prog: Program,
                ts_names: list[str], cfg: Config, timings: list[float] | None,
                warnings: list[str]) -> dict:
    runs = [r for r in runs if r.invocations]
    extracted = [_root_and_groups(r) for r in runs]
    data_runs = [(root, groups) for (root, groups), r in zip(extracted, runs) if r.has_data]
    mem_runs = [groups for (_, groups), r in zip(extracted, runs) if r.has_mem]

    if comp is not None:
        statements = comp.statements
    else:  # no composition: one application per child group, no edges
        idxs = sorted({g for _, groups in extracted for g in groups})
        statements = None
        warnings.append(f"{name}: no composition found, showing function applications without edges")

    n_groups = len(statements) if statements is not None else (max(idxs) + 1 if idxs else 0)
    if statements is not None:
        extra = sorted({g for _, groups in extracted for g in groups if g >= n_groups})
        if extra:
            warnings.append(f"{name}: trace has child groups {extra} beyond the composition's "
                            f"{n_groups} statements; they are ignored")

    apps = []
    set_aggs: dict[tuple[int, int], _SetAgg] = {}  # (app, entry index) -> aggregate
    for g in range(n_groups):
        runs_invs = [groups.get(g, []) for _, groups in extracted]
        data_invs = [groups.get(g, []) for _, groups in data_runs]
        ids = {inv.id for invs in runs_invs for inv in invs}
        if statements is not None:
            st = statements[g]
            if ids and ids != {st.func}:
                warnings.append(f"{name}: statement {g} applies '{st.func}', but the trace's group {g} "
                                f"contains {sorted(ids)}")
            fname = st.func
        else:
            st = None
            fname = ",".join(sorted(ids)) or "?"
        n_entries = max((len(inv.data) for invs in data_invs for inv in invs if inv.data), default=0)
        fn = _function_for(prog, fname, n_entries)
        n_slots = max(n_entries, len(fn.params))

        sets = []
        bound = {a.param: a for a in st.args} if st else {}
        for k in range(n_slots):
            agg = _SetAgg()
            for invs in data_invs:
                agg.add_run(invs, k)
            set_aggs[(g, k)] = agg
            if k < len(fn.params):
                pname, kind = fn.params[k], "in"
                arg = bound.get(pname)
                binding = f"{arg.dist + ' ' if arg.dist else ''}{', '.join(arg.sources)}" if arg else None
            elif k - len(fn.params) < len(fn.outputs):
                pname, kind = fn.outputs[k - len(fn.params)], "out"
                binding = st.outputs.get(pname) if st else None
            else:
                pname, kind, binding = f"d{k}", "in", None
            sets.append({"name": pname, "kind": kind, "binding": binding, "traced": bool(data_invs),
                         **agg.to_json()})
        traced_outs = {s["name"] for s in sets if s["kind"] == "out"}
        for oname in fn.outputs:
            if oname not in traced_outs:
                sets.append({"name": oname, "kind": "out", "binding": st.outputs.get(oname) if st else None,
                             "traced": False})

        node_counts = [len({inv.node for inv in invs}) for invs in runs_invs if invs]
        node_ids = sorted({inv.node for invs in runs_invs for inv in invs})
        apps.append({
            "idx": g,
            "fn": fname,
            "outs": [st.outputs[o] for o in fn.outputs if o in st.outputs] if st else [],
            "by": st.by if st else None,
            "inv": _stat([len(invs) for invs in runs_invs]),
            "nodes": {"count": _stat(node_counts), "ids": node_ids},
            "sets": sets,
            "lat": _latency(runs_invs, ts_names, cfg),
            "mem": _memory([groups.get(g, []) for groups in mem_runs]),
            "_fn": fn,
        })

    edges = []
    comp_inputs, comp_outputs = [], []
    if comp is not None:
        producers: dict[str, tuple[int, str]] = {}  # composition set -> (app, function output)
        for g, st in enumerate(comp.statements):
            for out, target in st.outputs.items():
                producers[target] = (g, out)

        # Composition inputs/outputs as recorded on the root invocation (usually all zero)
        root_aggs = []
        n_root = max(len(comp.inputs) + len(comp.outputs),
                     max((len(root.data) for root, _ in data_runs if root and root.data), default=0))
        for k in range(n_root):
            agg = _SetAgg()
            for root, _ in data_runs:
                agg.add_run([root] if root else [], k)
            root_aggs.append(agg)
        n_root_entries = max((len(root.data) for root, _ in data_runs if root and root.data), default=0)
        comp_inputs = [{"name": n, **root_aggs[k].totals()} for k, n in enumerate(comp.inputs)]
        comp_outputs = [{"name": n} for n in comp.outputs]

        derived: dict[str, list[dict]] = {}  # composition set -> estimates from its consumers
        for g, st in enumerate(comp.statements):
            fn = apps[g]["_fn"]
            for arg in st.args:
                if arg.param not in fn.params:
                    warnings.append(f"{name}: statement {g} binds unknown input set '{arg.param}' of {fn.name}")
                    continue
                k = fn.params.index(arg.param)
                agg = set_aggs[(g, k)]
                for src in arg.sources:
                    if src in producers:
                        frm = {"kind": "app", "ref": producers[src][0]}
                    elif src in comp.inputs:
                        frm = {"kind": "in", "ref": src}
                    else:
                        warnings.append(f"{name}: set '{src}' (statement {g}) is never produced")
                        frm = {"kind": "in", "ref": src}
                        if src not in [c["name"] for c in comp_inputs]:
                            comp_inputs.append({"name": src, "items": None, "size": None, "undefined": True})
                    edges.append({
                        "from": frm, "to": {"kind": "app", "ref": g}, "set": src, "param": arg.param,
                        "dist": arg.dist, "shared": len(arg.sources),
                        "traced": bool(data_runs), **agg.to_json(),
                    })
                    if len(arg.sources) == 1 and data_runs:
                        est = agg.per_inv_max() if arg.dist == "all" else agg.totals()
                        derived.setdefault(src, []).append(
                            {**est, "via": f"{arg.param} of #{g} {fn.name} ({arg.dist or 'default'})"})

        for k, out in enumerate(comp.outputs):
            if out not in producers:
                warnings.append(f"{name}: composition output '{out}' is never produced")
                continue
            entry = len(comp.inputs) + k
            traced = entry < n_root_entries
            edges.append({
                "from": {"kind": "app", "ref": producers[out][0]}, "to": {"kind": "out", "ref": out},
                "set": out, "param": None, "dist": None, "shared": 1, "traced": traced,
                **(root_aggs[entry].to_json() if traced else {"items": None, "size": None}),
            })

        # Attach consumer-based estimates to untraced output sets
        for app in apps:
            for s in app["sets"]:
                if s["kind"] == "out" and not s["traced"] and s["binding"] in derived:
                    ests = derived[s["binding"]]
                    best = max(ests, key=lambda e: (e["size"] or {}).get("mean", 0))
                    s.update({"items": best["items"], "size": best["size"], "estimate": best["via"]})

    for app in apps:
        del app["_fn"]

    return {
        "name": name,
        "composition": comp.name if comp else None,
        "nRuns": len(runs),
        "nDataRuns": len(data_runs),
        "latency": _stat(timings) if timings else None,
        "traceLatency": _stat([v for v in (_root_latency(r) for r in runs) if v is not None]),
        "invocations": _stat([len(r.invocations) for r in runs]),
        "apps": apps,
        "inputs": comp_inputs,
        "outputs": comp_outputs,
        "edges": edges,
    }


def build_data(trace: Trace, prog: Program, cfg: Config, timings: dict[str, list[float]],
               warnings: list[str]) -> dict:
    names = sorted(set(trace.queries) | set(timings), key=_natural_key)
    queries = []
    for q in names:
        if q not in trace.queries:
            warnings.append(f"{q}: only in the timings file, skipped")
            continue
        queries.append(build_query(q, trace.queries[q], prog.compositions.get(q), prog,
                                   trace.ts_names, cfg, timings.get(q), warnings))
    return {"queries": queries, "warnings": warnings}


def render(trace: Trace, prog: Program, cfg: Config, timings: dict[str, list[float]],
           title: str, warnings: list[str]) -> str:
    data = json.dumps(build_data(trace, prog, cfg, timings, warnings), separators=(",", ":"))
    data = data.replace("</", "<\\/")  # keep the JSON from terminating its <script> element

    html = (TEMPLATE_DIR / "dataflow.html").read_text()
    css = (TEMPLATE_DIR / "dataflow.css").read_text()
    js = (TEMPLATE_DIR / "dataflow.js").read_text()
    replacements = {"{{TITLE}}": escape(title), "{{CSS}}": css, "{{JS}}": js, "{{DATA}}": data}
    return re.sub(r"\{\{(TITLE|CSS|JS|DATA)\}\}", lambda m: replacements[m.group(0)], html)
