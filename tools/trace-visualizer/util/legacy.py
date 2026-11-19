"""Parser for the legacy JSON-like `timestamps.txt` trace format.

The legacy format consists of blocks of the form

    Query <name>:
    <JSON: a single run object or a list of run objects>

where each run object is a tree of invocations. Two invocation layouts are
accepted:

- old: "id", "ts", "node id", "items", "input size", "children"
- new: "id", "ts", "nodeId", "data" (a list of {"items", "size"}), "maxMem", "children"

"children" is a list of child groups, each being a list of invocations. In the
new layout, "ts" and "data" are each optional, but at least one must be present;
within one run, either all invocations have a field or none do. "maxMem" (bytes, also
accepted as "max_mem") is optional; if any invocation of a run has it, the others are
stored with 0 (not recorded). Timestamp names
are not stored in the file; they are implied by LEGACY_TS_NAMES.
"""

import json
import re

from .model import DataEntry, Invocation, Run, Trace

LEGACY_TS_NAMES = [
    "DeserializationEnd",
    "EnterDispatcher",
    "DynamicParsingEnd",
    "ShardingStart",
    "IOQueueStart",
    "IOQueueEnd",
    "ComputeQueueStart",
    "ComputeQueueEnd",
    "MasterFetchStart",
    "MasterFetchEnd",
    "RemoteTake",
    "RemoteIOQueueStart",
    "RemoteIOQueueEnd",
    "RemoteComputeQueueStart",
    "RemoteComputeQueueEnd",
    "FetchingStart",
    "FetchingEnd",
    "ParsingStart",
    "ParsingEnd",
    "LoadStart",
    "TransferStart",
    "EngineStart",
    "EngineEnd",
    "FutureReturn",
]

_QUERY_HEADER = re.compile(r"^Query\s+(.+?):\s*$", re.MULTILINE)


def _flatten(node: dict, parent: int | None, group: int, run: Run) -> None:
    """Append `node` and its descendants in pre-order, so parents always precede children."""
    ts = node.get("ts")
    if ts is not None and len(ts) != len(LEGACY_TS_NAMES):
        raise ValueError(f"invocation '{node['id']}' has {len(ts)} timestamps, expected {len(LEGACY_TS_NAMES)}")

    if "data" in node:
        data = [DataEntry(d.get("items", 0), d.get("size", 0)) for d in node["data"]]
    elif "items" in node or "input size" in node:
        data = [DataEntry(node.get("items", 0), node.get("input size", 0))]
    else:
        data = None
    if ts is None and data is None:
        raise ValueError(f"invocation '{node['id']}' has neither timestamps nor data")

    idx = len(run.invocations)
    if run.invocations:
        first = run.invocations[0]
        if (first.ts is None) != (ts is None) or (first.data is None) != (data is None):
            raise ValueError(f"invocation '{node['id']}': all invocations of a run must either "
                             "have timestamps (data) or not")
    run.invocations.append(Invocation(
        id=node["id"],
        parent=parent,
        group=group,
        node=node.get("nodeId", node.get("node id", 0)),
        ts=None if ts is None else list(ts),
        data=data,
        max_mem=node.get("maxMem", node.get("max_mem")),
    ))
    for group_idx, children in enumerate(node.get("children", [])):
        for child in children:
            _flatten(child, idx, group_idx, run)


def loads(content: str) -> Trace:
    trace = Trace(ts_names=list(LEGACY_TS_NAMES))
    headers = list(_QUERY_HEADER.finditer(content))
    for i, m in enumerate(headers):
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        body = json.loads(content[m.end():body_end])
        runs = body if isinstance(body, list) else [body]
        if not runs:
            continue
        query_runs = trace.queries.setdefault(m.group(1).strip(), [])
        for root in runs:
            run = Run()
            _flatten(root, None, 0, run)
            if any(inv.max_mem is not None for inv in run.invocations):
                for inv in run.invocations:
                    if inv.max_mem is None:
                        inv.max_mem = 0
            query_runs.append(run)
    return trace


def read(path: str) -> Trace:
    with open(path) as f:
        return loads(f.read())
