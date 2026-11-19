# Trace Visualizer

Renders trace files into a single self-contained, interactive HTML file.

```sh
# Render one or more traces (several traces are shown stacked and time-synced)
python3 tracevis.py render a.plmt b.plmt -o viewer.html
python3 tracevis.py render a.plmt -c my_config.json --labels baseline
python3 tracevis.py render a.plmt.gz b.plmt.xz -o viewer.html   # compressed traces

# Convert a timestamps.txt file (blocks of `Query <name>:` followed by JSON) into the binary format
python3 tracevis.py convert timestamps.txt -o trace.plmt
python3 tracevis.py convert timestamps.txt -o trace.plmt.xz   # compressed with xz (or .gz for gzip)
```

Trace files are compressed with gzip or xz when their name ends in `.gz` or `.xz`, both when writing and reading.

`convert` accepts both the old invocation layout (`node id`, `items`, `input size`) and the new one
(`nodeId`, `data`, see `example.json`). In the new layout, `ts`, `data` and `maxMem` (maximum memory of the invocation in bytes) are each optional.
Runs without timestamps are shown empty in the viewer.

The trace format is specified in [FORMAT.md](FORMAT.md).

## Dataflow graph

Shows the execution graph of one query at a time (selectable) in a self-contained interactive HTML page.

```sh
python3 dataflow.py traces.plmt.gz -o dataflow.html                    # *.ddsl and timings.txt next to the trace
python3 dataflow.py traces.plmt.gz --ddsl compositions/ --timings timings.txt -c config/dataflow.json
```

- **Nodes** are the function applications (statements) of the query's composition, labeled with their output set(s),
  number of invocations and wall-clock latency. The thin bar at the bottom shows when the application was active
  relative to the query's traced latency. Composition inputs/outputs are drawn as pills (inputs can be hidden).
- **Edges** are the dataflow from a set into an input set of an application, labeled with the input set and colored by
  distribution (`all`, `each`, `keyed`). Their width shows the mean size or item count (log, √ or linear scale);
  dashed edges have no data recorded.
- **Hovering** (click to pin, Esc to close) shows for an edge the mean size/items with min/max across runs and the
  per-invocation range; for a node the number of invocations, the nodes it ran on (distinct node ids), the
  execution latency (wall clock, per invocation, mean phase durations from the config), the maximum memory
  (largest invocation, per-invocation mean/min/max and sum, if the trace has `max_mem`) and for every input and
  output set its items/size with the least and most per invocation.
- The header shows the mean query latency from the timings file (`Query <name>: <ms>,<ms>,...`, one value per run)
  and the latency of the trace's root invocation.

The trace is matched to the composition of the same name: child group `g` of the root invocation holds the
invocations of statement `g`, and the data entries of an invocation are its input sets in parameter order
(further entries, if present, are taken as output sets). The data of an edge is the sum over the consuming
invocations, so an `all` input counts once per invocation. Output sets are not traced; their totals are estimated
from their consumers (marked with ≈). `config/dataflow.json` defines the latency phases for the current
timestamp names; timestamps a config references but the trace lacks are treated as unset.

## Visualization config

The config (default: `config/default.json`) defines which bars are drawn from which timestamps.

```json
{
  "span":   {"start": ["IOQueueStart", "EngineStart", 0], "end": ["FutureReturn", "EngineEnd"]},
  "remote": "RemoteTake",
  "bars": [
    {"label": "IO Queue",    "start": "IOQueueStart", "end": "IOQueueEnd", "color": "#F9B8D3"},
    {"label": "Load Binary", "start": "LoadStart",    "end": ["TransferStart", "EngineStart"]}
  ]
}
```

- **References**: `start`/`end` are either a single reference or a list of them. A reference is a timestamp name from the trace header, or a number (a fixed time in trace units, i.e. µs). The first reference that is set is used: timestamps count as unset when they are `0`, numbers are always set. All names are checked against the trace header.
- **`bars`** (required, drawn in order): `label`, `start`, `end`, and optional `color` (`#RGB`/`#RRGGBB`; the outline is derived from it). Bars without a color get evenly spaced hues. A bar is skipped for an invocation if its start or end is unset; if start > end, start is clamped to end.
- **`span`** (optional): the extent of an invocation's background bar. Without it (or when it is unset), it covers all of the invocation's bars.
- **`remote`** (optional): timestamp that marks an invocation as executed remotely when set.

## Layout

```
tracevis.py            CLI entry point
dataflow.py            dataflow graph CLI
config/default.json    default visualization config
config/dataflow.json   latency phases for the dataflow graph
util/model.py          in-memory trace model
util/trace_format.py   binary format encoder/decoder
util/legacy.py         legacy timestamps.txt parser
util/config.py         config loading/validation
util/layout.py         bar computation and row (slot) packing
util/html.py           HTML rendering
util/ddsl.py           composition (.ddsl) parser
util/dataflow.py       per-application aggregation for the dataflow graph
util/templates/        viewer HTML/CSS/JS
```
