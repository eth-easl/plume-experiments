"""Renders laid-out traces into a single self-contained HTML file."""

import json
import re
from html import escape
from pathlib import Path

from .config import Config
from .layout import layout_run
from .model import Trace

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _natural_key(name: str):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def build_data(traces: list[tuple[str, Trace]], cfg: Config) -> dict:
    query_names = sorted({q for _, t in traces for q in t.queries}, key=_natural_key)
    js_traces = []
    for label, trace in traces:
        js_traces.append({
            "name": label,
            "queries": {
                qname: {"runs": [layout_run(run, trace.ts_names, cfg) for run in runs]}
                for qname, runs in trace.queries.items()
            },
        })
    return {
        "traces": js_traces,
        "queryNames": query_names,
        "bars": [{"label": b.label, "face": b.face, "edge": b.edge} for b in cfg.bars],
    }


def render(traces: list[tuple[str, Trace]], cfg: Config, title: str = "Trace Viewer") -> str:
    data = json.dumps(build_data(traces, cfg), separators=(",", ":"))
    # Keep the embedded JSON from terminating its <script> element early
    data = data.replace("</", "<\\/")

    html = (TEMPLATE_DIR / "viewer.html").read_text()
    css = (TEMPLATE_DIR / "viewer.css").read_text()
    js = (TEMPLATE_DIR / "viewer.js").read_text()
    replacements = {"{{TITLE}}": escape(title), "{{CSS}}": css, "{{JS}}": js, "{{DATA}}": data}
    return re.sub(r"\{\{(TITLE|CSS|JS|DATA)\}\}", lambda m: replacements[m.group(0)], html)


def write(traces: list[tuple[str, Trace]], cfg: Config, path: str, title: str = "Trace Viewer") -> None:
    with open(path, "w") as f:
        f.write(render(traces, cfg, title))
