"""Turns decoded runs into the bar/slot layout consumed by the HTML viewer."""

from .config import Config, Ref
from .model import Run

US_PER_MS = 1000


def _resolve(refs: list[Ref], ts: list[int], index: dict[str, int]) -> float | None:
    """Value of the first reference that is set (non-zero timestamp or any literal), in ms."""
    for r in refs:
        if isinstance(r, str):
            v = ts[index[r]]
            if v:
                return v / US_PER_MS
        else:
            return r / US_PER_MS
    return None


def _find_slot(start: float, end: float, busy_until: list[float]) -> int:
    for i, t in enumerate(busy_until):
        if start > t:
            busy_until[i] = end
            return i
    busy_until.append(end)
    return len(busy_until) - 1


def _r3(v: float) -> float:
    return round(v, 3)


def layout_run(run: Run, ts_names: list[str], cfg: Config) -> dict:
    index = {name: i for i, name in enumerate(ts_names)}

    # Every (parent, group) pair gets a run-wide group id, numbered in pre-order
    group_ids: dict[tuple[int, int], int] = {}
    group_sizes: dict[int, int] = {}

    invocations = []
    for inv in run.invocations:
        if inv.ts is None:
            continue  # no timing information, nothing to draw
        phases = []
        for bar in cfg.bars:
            s = _resolve(bar.start, inv.ts, index)
            e = _resolve(bar.end, inv.ts, index)
            if s is None or e is None:
                phases.append(None)
                continue
            phases.append([_r3(min(s, e)), _r3(e)])

        present = [p for p in phases if p]
        start = _resolve(cfg.span_start, inv.ts, index)
        end = _resolve(cfg.span_end, inv.ts, index)
        if start is None:
            start = min((p[0] for p in present), default=None)
        if end is None:
            end = max((p[1] for p in present), default=None)
        if start is None or end is None:
            continue  # nothing recorded for this invocation

        group = child_index = None
        if inv.parent is not None:
            key = (inv.parent, inv.group)
            group = group_ids.setdefault(key, len(group_ids))
            child_index = group_sizes.get(group, 0)
            group_sizes[group] = child_index + 1

        invocations.append({
            "id": inv.id,
            "group_index": inv.group if inv.parent is not None else None,
            "child_index": child_index,
            "group": group,
            "slot": 0,
            "start": _r3(start),
            "end": _r3(max(start, end)),
            "on_remote": bool(cfg.remote and inv.ts[index[cfg.remote]]),
            "node_id": inv.node,
            "data": None if inv.data is None else [[d.items, d.size] for d in inv.data],
            "phases": phases,
        })

    for inv in invocations:
        inv["group_size"] = group_sizes[inv["group"]] if inv["group"] is not None else None

    # Sort by group (tree order, roots last), longest first, then pack greedily into slots
    invocations.sort(key=lambda x: (x["group"] if x["group"] is not None else float("inf"),
                                    -(x["end"] - x["start"])))
    busy_until: list[float] = []
    for inv in invocations:
        inv["slot"] = _find_slot(inv["start"], inv["end"], busy_until)

    return {
        "invocations": invocations,
        "num_slots": len(busy_until) or 1,
        "max_time": _r3(max((i["end"] for i in invocations), default=0)),
    }
