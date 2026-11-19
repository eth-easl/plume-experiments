#!/usr/bin/env python3
"""
Trace visualizer: renders binary trace files into an interactive HTML viewer.

Usage:
    tracevis.py render TRACE [TRACE ...] [-c CONFIG] [-o OUTPUT] [--labels NAME ...]
    tracevis.py convert LEGACY_TXT -o TRACE
"""

import argparse
import sys
from pathlib import Path

from util import config, html, legacy, trace_format

DEFAULT_CONFIG = Path(__file__).parent / "config" / "default.json"


def _stem(path: str) -> str:
    """File name without its extension, ignoring a compression suffix (`a.plmt.gz` -> `a`)."""
    p = Path(path)
    if p.suffix in trace_format.COMPRESSIONS:
        p = p.with_suffix("")
    return p.stem


def trace_labels(paths: list[str]) -> list[str]:
    """File stems, falling back to `<parent dir>/<stem>` and then to the full file name when they collide."""
    stems = [_stem(p) for p in paths]
    labels = [f"{Path(p).resolve().parent.name}/{s}" if stems.count(s) > 1 else s
              for p, s in zip(paths, stems)]
    return [Path(p).name if labels.count(l) > 1 else l for p, l in zip(paths, labels)]


def cmd_render(args) -> None:
    labels = args.labels or trace_labels(args.traces)
    if len(labels) != len(args.traces):
        sys.exit(f"Error: got {len(labels)} labels for {len(args.traces)} traces")

    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        sys.exit(f"Error in config {args.config}: {e}")

    traces = []
    for label, path in zip(labels, args.traces):
        print(f"Reading {path}...")
        try:
            trace = trace_format.read(path)
        except trace_format.TraceFormatError as e:
            sys.exit(f"Error reading {path}: {e}")
        all_runs = [r for runs in trace.queries.values() for r in runs]
        n_no_ts = sum(1 for r in all_runs if r.invocations and not r.has_ts)
        if n_no_ts < sum(1 for r in all_runs if r.invocations):
            unknown = cfg.referenced_names() - set(trace.ts_names)
            if unknown:
                sys.exit(f"Error: config references timestamps not in {path}: {', '.join(sorted(unknown))}")
        n_invs = sum(len(r.invocations) for r in all_runs)
        print(f"  {len(trace.queries)} queries, {n_invs} total invocations")
        if n_no_ts:
            print(f"  Note: {n_no_ts} run(s) have no timestamps and will be shown empty")
        traces.append((label, trace))

    html.write(traces, cfg, args.output, args.title)
    print(f"Written: {args.output}")


def cmd_convert(args) -> None:
    trace = legacy.read(args.input)
    trace_format.write(trace, args.output)
    n_invs = sum(len(r.invocations) for runs in trace.queries.values() for r in runs)
    print(f"Written: {args.output} ({len(trace.queries)} queries, {n_invs} invocations)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("render", help="Generate an interactive HTML viewer from trace files")
    p.add_argument("traces", nargs="+", metavar="TRACE", help="Binary trace file(s), optionally compressed (.gz, .xz)")
    p.add_argument("-c", "--config", default=str(DEFAULT_CONFIG),
                   help="Visualization config (default: config/default.json)")
    p.add_argument("-o", "--output", default="trace_viewer.html",
                   help="Output HTML file (default: trace_viewer.html)")
    p.add_argument("--labels", nargs="+", metavar="NAME",
                   help="Display names for the traces (default: file names)")
    p.add_argument("--title", default="Trace Viewer", help="HTML page title")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("convert", help="Convert a legacy timestamps.txt file to the binary format")
    p.add_argument("input", metavar="LEGACY_TXT")
    p.add_argument("-o", "--output", required=True, metavar="TRACE",
                   help="Output trace file; compressed if it ends in .gz or .xz (e.g. trace.plmt.gz)")
    p.set_defaults(func=cmd_convert)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
