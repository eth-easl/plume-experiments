#!/usr/bin/env python3
"""
Dataflow graph viewer: renders the execution graph of every query in a trace as an
interactive HTML page. Nodes are the function applications of the query's composition,
edges the dataflow between them, sized by the amount of data transferred.

Usage:
    dataflow.py TRACE [--ddsl FILE|DIR ...] [--timings FILE] [-c CONFIG] [-o OUTPUT] [--title TITLE]

Without --ddsl, all *.ddsl files next to the trace are used. Without --timings, a
timings.txt next to the trace is used if it exists.
"""

import argparse
import sys
from pathlib import Path

from util import config, dataflow, ddsl, trace_format

DEFAULT_CONFIG = Path(__file__).parent / "config" / "dataflow.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("trace", metavar="TRACE", help="Binary trace file, optionally compressed (.gz, .xz)")
    parser.add_argument("--ddsl", nargs="+", metavar="PATH",
                        help="Composition file(s) or directories with *.ddsl files (default: next to the trace)")
    parser.add_argument("--timings", metavar="FILE",
                        help="End-to-end latencies, lines 'Query <name>: <ms>,<ms>,...' "
                             "(default: timings.txt next to the trace, if present)")
    parser.add_argument("-c", "--config", default=str(DEFAULT_CONFIG),
                        help="Visualization config defining the latency phases (default: config/dataflow.json)")
    parser.add_argument("-o", "--output", default="dataflow.html", help="Output HTML file (default: dataflow.html)")
    parser.add_argument("--title", default=None, help="HTML page title (default: Dataflow – <trace name>)")
    args = parser.parse_args()

    trace_dir = Path(args.trace).resolve().parent

    try:
        cfg = config.load(args.config)
    except config.ConfigError as e:
        sys.exit(f"Error in config {args.config}: {e}")

    print(f"Reading {args.trace}...")
    try:
        trace = trace_format.read(args.trace)
    except trace_format.TraceFormatError as e:
        sys.exit(f"Error reading {args.trace}: {e}")
    unknown = cfg.referenced_names() - set(trace.ts_names)
    if unknown and trace.ts_names:
        print(f"  Note: config references timestamps not in the trace (treated as unset): {', '.join(sorted(unknown))}")
    print(f"  {len(trace.queries)} queries")

    ddsl_paths = args.ddsl or [str(trace_dir)]
    try:
        prog = ddsl.read(ddsl_paths)
    except (ddsl.DdslError, OSError) as e:
        sys.exit(f"Error reading compositions: {e}")
    print(f"  {len(prog.compositions)} compositions from {', '.join(ddsl_paths)}")

    timings_path = args.timings or (str(trace_dir / "timings.txt") if (trace_dir / "timings.txt").exists() else None)
    timings = {}
    if timings_path:
        try:
            timings = dataflow.read_timings(timings_path)
        except (OSError, ValueError) as e:
            sys.exit(f"Error reading timings {timings_path}: {e}")
        print(f"  timings for {len(timings)} queries from {timings_path}")
    else:
        print("  no timings file, the query latency is taken from the trace")

    warnings: list[str] = []
    title = args.title or f"Dataflow – {trace_format_stem(args.trace)}"
    html = dataflow.render(trace, prog, cfg, timings, title, warnings)
    for w in warnings:
        print(f"  Warning: {w}")
    with open(args.output, "w") as f:
        f.write(html)
    print(f"Written: {args.output}")


def trace_format_stem(path: str) -> str:
    p = Path(path)
    if p.suffix in trace_format.COMPRESSIONS:
        p = p.with_suffix("")
    return f"{p.resolve().parent.name}/{p.stem}"


if __name__ == "__main__":
    main()
