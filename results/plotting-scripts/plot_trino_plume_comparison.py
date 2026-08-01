#!/usr/bin/env python3
"""Side-by-side open-loop comparison of two systems (Trino | Plume).

2 columns x 3 rows. Left column = system A (Trino), right column = system B
(Plume). Rows share a y-axis so the two systems are directly comparable:

  row 1  arrival rate      submitted queries per 15 s (open-loop submissions)
  row 2  query latency     one dot per query at its arrival time; dot height is
                           the open-loop latency, dot color is that query's
                           (open - closed) delta
  row 3  latency delta     the same per-query delta as a bar at the query's
                           arrival time

Rows 2 and 3 share one RdYlGn_r color scale (as in plot_combined.py: linear over
the real delta range, so color is proportional to the delta value), pooled across
both systems so a color means the same thing in every panel.

The first and last TRIM_MIN minutes of the trace are dropped (warm-up / drain)
and the x-axis is re-zeroed at the start of the kept window.

A third figure is emitted when --a-scaling / --b-scaling are given: a 2x2 grid of
the latency delta only, with the fixed-size runs on the top row and the runs that
scale out mid-trace on the bottom row, zoomed to --zoom minutes so the scale-out
is legible. --scale-events marks when workers were added.

Inputs use the run-CSV schema from records_to_run_csv.py:
  seq,query_id,status,start_s,end_s,rel_start_s,rel_end_s,latency_s

Usage:
  plot_side_by_side.py <A_open.csv> <A_closed.csv> <B_open.csv> <B_closed.csv>
                       <out.png> [labelA] [labelB]
                       [--a-scaling A_open_scaling.csv]
                       [--b-scaling B_open_scaling.csv]
                       [--scale-events 843:7,846:8,855:9] [--all-scale-events]
                       [--zoom LO HI]
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.ticker import MultipleLocator

# fonttype 42 embeds TrueType rather than Type 3, which most CS venues require
plt.rcParams.update({"font.size": 26, "pdf.fonttype": 42, "ps.fonttype": 42})


def _scale_events(s):
    """"843:7,846:8" -> [(843.0, 7), (846.0, 8)], seconds on the raw run clock."""
    if not s:
        return []
    out = []
    for part in s.split(","):
        t, n = part.split(":")
        out.append((float(t), int(n)))
    return sorted(out)


_p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_p.add_argument("a_open")
_p.add_argument("a_closed")
_p.add_argument("b_open")
_p.add_argument("b_closed")
_p.add_argument("out")
_p.add_argument("label_a", nargs="?", default="Trino")
_p.add_argument("label_b", nargs="?", default="Plume")
_p.add_argument("--a-scaling", help="open-loop run of A that scales out mid-trace")
_p.add_argument("--b-scaling", help="open-loop run of B that scales out mid-trace")
_p.add_argument("--scale-events", type=_scale_events, default="0:6,843:7,846:8,855:9",
                help="second:total_nodes pairs, on the raw (untrimmed) run clock")
_p.add_argument("--all-scale-events", action="store_true",
                help="mark every event; by default only the last one is drawn, "
                     "since the earlier ones are seconds away from it")
_p.add_argument("--zoom", nargs=2, type=float, default=(8.5, 10.5),
                metavar=("LO", "HI"),
                help="x window of the 2x2 delta figure, in trimmed-plot minutes")
_args = _p.parse_args()

A_OPEN, A_CLOSED = _args.a_open, _args.a_closed
B_OPEN, B_CLOSED = _args.b_open, _args.b_closed
OUT = _args.out
LABEL_A, LABEL_B = _args.label_a, _args.label_b

OK = ["completed", "success"]
BIN_S = 15.0     # arrival-rate bin width
TRIM_MIN = 5.0   # drop this many minutes of warm-up and drain from each end

# same colormap as plot_combined.py
DELTA_CMAP = plt.get_cmap("RdYlGn_r")
UNMATCHED = "#9ca3af"  # open-loop query with no closed-loop counterpart


def load(open_csv, closed_csv):
    op = pd.read_csv(open_csv)
    cl = pd.read_csv(closed_csv)
    op_ok = op[op["status"].isin(OK)]
    cl_ok = cl[cl["status"].isin(OK)]
    failed = op[~op["status"].isin(OK)]

    # left join on seq, the trace position: every run replays the same trace in
    # the same order, so seq pairs a query with itself across runs. query_id is
    # not usable as the key -- it repeats within a run for some engines, and the
    # Plume CSVs disagree on whether it carries a "_<seq>" suffix.
    m = op_ok[["seq", "rel_start_s", "latency_s"]].merge(
        cl_ok[["seq", "latency_s"]], on="seq", how="left",
        suffixes=("_open", "_closed"),
    ).sort_values("rel_start_s")

    return {
        # every open-loop submission, failures included, for the arrival rate
        "t_all": op["rel_start_s"].to_numpy() / 60.0,
        "x": m["rel_start_s"].to_numpy() / 60.0,
        "lat": m["latency_s_open"].to_numpy(),
        "lat_closed": m["latency_s_closed"].to_numpy(),
        "delta": (m["latency_s_open"] - m["latency_s_closed"]).to_numpy(),
        "failed_x": failed["rel_start_s"].to_numpy() / 60.0,
    }


def trim(d, t0, t1):
    """Keep arrivals in [t0, t1] minutes and re-zero the clock at t0."""
    mx = (d["x"] >= t0) & (d["x"] <= t1)
    mf = (d["failed_x"] >= t0) & (d["failed_x"] <= t1)
    ta = d["t_all"][(d["t_all"] >= t0) & (d["t_all"] <= t1)]
    edges = np.arange(0.0, (t1 - t0) * 60.0 + BIN_S, BIN_S)
    counts, _ = np.histogram((ta - t0) * 60.0, bins=edges)
    return {
        "x": d["x"][mx] - t0,
        "lat": d["lat"][mx],
        "lat_closed": d["lat_closed"][mx],
        "delta": d["delta"][mx],
        "failed_x": d["failed_x"][mf] - t0,
        "n_failed": int(mf.sum()),
        "rate_t": edges[:-1] / 60.0,
        "rate_n": counts,
    }


A_raw = load(A_OPEN, A_CLOSED)
B_raw = load(B_OPEN, B_CLOSED)

# one window shared by both systems so the columns stay aligned
T_END = max(A_raw["t_all"].max(), B_raw["t_all"].max())
T0, T1 = TRIM_MIN, T_END - TRIM_MIN
A, B = trim(A_raw, T0, T1), trim(B_raw, T0, T1)
cols = [(A, LABEL_A), (B, LABEL_B)]

# one color scale for rows 2 and 3, pooled across both systems
all_delta = np.concatenate([A["delta"], B["delta"]])
all_delta = all_delta[~np.isnan(all_delta)]
dlo, dhi = float(all_delta.min()), float(all_delta.max())
delta_norm = Normalize(vmin=dlo, vmax=dhi)

fig, axes = plt.subplots(3, 2, figsize=(20, 11), sharex="col", sharey="row",
                         layout="constrained")

for c, (d, label) in enumerate(cols):
    ax_rate, ax_lat, ax_del = axes[0, c], axes[1, c], axes[2, c]
    have = ~np.isnan(d["delta"])

    # --- row 1: arrival rate -------------------------------------------------
    ax_rate.fill_between(d["rate_t"], d["rate_n"], step="post",
                         color="#f59e0b", alpha=0.35)
    ax_rate.step(d["rate_t"], d["rate_n"], where="post", color="#f59e0b", lw=2)
    ax_rate.set_title(label, pad=12)
    ax_rate.grid(True, alpha=0.25)

    # --- row 2: latency, dots colored by that query's delta ------------------
    if (~have).any():
        ax_lat.scatter(d["x"][~have], d["lat"][~have], color=UNMATCHED, s=26,
                       alpha=0.8, edgecolors="none")
    # largest |delta| drawn last so the outliers are not buried
    o = np.argsort(np.abs(d["delta"][have]))
    ax_lat.scatter(d["x"][have][o], d["lat"][have][o], c=d["delta"][have][o],
                   cmap=DELTA_CMAP, norm=delta_norm, s=26, alpha=0.9,
                   edgecolors="none")
    if d["n_failed"]:
        ax_lat.scatter(d["failed_x"], [0.97] * d["n_failed"], marker="x",
                       color="#dc2626", s=70, linewidths=2.2, zorder=5,
                       transform=ax_lat.get_xaxis_transform(), clip_on=False,
                       label=f"failed ({d['n_failed']})")
        # dropped below the top edge so the box clears the failed markers
        ax_lat.legend(loc="upper right", bbox_to_anchor=(1.0, 0.90),
                      fontsize=20, framealpha=0.9, handletextpad=0.3,
                      borderpad=0.3)
    ax_lat.grid(True, alpha=0.25)

    # --- row 3: the same delta as bars ---------------------------------------
    dx, dv = d["x"][have], d["delta"][have]
    bar_w = (np.ptp(dx) or 1.0) / max(len(dx), 1) * 1.5
    ax_del.bar(dx, dv, width=bar_w, color=DELTA_CMAP(delta_norm(dv)))
    ax_del.axhline(0, color="#333333", lw=1)
    ax_del.grid(True, axis="y", alpha=0.25)
    ax_del.set_xlabel("Arrival time (min)")
    ax_del.set_xlim(0, T1 - T0)
    ax_del.xaxis.set_major_locator(MultipleLocator(5))

axes[0, 0].set_ylabel(f"Arrival rate\n")
axes[1, 0].set_ylabel("Query\nlatency (s)")
axes[2, 0].set_ylabel("Latency delta (s)\nopen-closed loop")

for ax in axes.ravel():
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

# one colorbar for rows 2-3, inset into the empty upper-right of the last panel
cax = axes[2, 1].inset_axes([0.50, 0.86, 0.44, 0.055])  # [x0, y0, w, h] axes frac
cb = fig.colorbar(ScalarMappable(norm=delta_norm, cmap=DELTA_CMAP), cax=cax,
                  orientation="horizontal")
cb.set_label("delta (s)", fontsize=18, labelpad=2)
# tick at the real data minimum (negative), then 0 and 20 s steps up to the max
pos_ticks = np.arange(0, np.floor(dhi) + 1, 20)
cb.set_ticks(np.concatenate([[dlo], pos_ticks]))
cb.set_ticklabels([f"{dlo:.0f}"] + [f"{t:.0f}" for t in pos_ticks])
cb.ax.tick_params(labelsize=15, pad=1)
cb.outline.set_linewidth(0.6)

fig.savefig(OUT, dpi=150)
print(f"saved {OUT}  (kept {T0:.1f}-{T1:.1f} min of the trace, "
      f"replotted as 0-{T1 - T0:.1f} min)")
for d, label in cols:
    v = d["delta"][~np.isnan(d["delta"])]
    print(f"  {label:<8} matched={len(v):4d} unmatched={int(np.isnan(d['delta']).sum()):2d} "
          f"failed={d['n_failed']:2d}  median delta={np.median(v):+.2f}s  "
          f"p95={np.percentile(v, 95):+.2f}s  max={v.max():+.2f}s")


# --- second figure: latency CDFs, all four runs on one axes --------------------
# identity is carried by color (system) and line style (loop), never by color
# alone. Same trimmed query set as the main figure.
def _cdf(v):
    v = np.sort(v[~np.isnan(v)])
    return v, np.arange(1, len(v) + 1) / len(v)


SYS_COLOR = {LABEL_A: "cornflowerblue", LABEL_B: "darkorange"}

figc, axc = plt.subplots(figsize=(9, 6), layout="constrained")
for d, label in cols:
    for key, loop, ls in [("lat", "open", "-"), ("lat_closed", "closed", "--")]:
        xs, ys = _cdf(d[key])
        axc.step(xs, ys, where="post", lw=2.8, ls=ls, color=SYS_COLOR[label],
                 label=f"{label} {loop} loop")
axc.set_xscale("log")
axc.set_xlabel("Query latency (s)")
axc.set_ylabel("CDF")
axc.set_ylim(0, 1)
axc.grid(True, which="both", alpha=0.25)
# lower right is the one corner all four curves stay clear of
axc.legend(loc="lower right", fontsize=24, framealpha=0.9, handlelength=1.6,
           handletextpad=0.4, borderpad=0.3, labelspacing=0.2)
for s in ("top", "right"):
    axc.spines[s].set_visible(False)

_out = Path(OUT)
cdf_out = str(_out.with_name(_out.stem + "_cdf" + _out.suffix))
figc.savefig(cdf_out, dpi=150)
print(f"saved {cdf_out}")
for d, label in cols:
    for key, loop in [("lat", "open"), ("lat_closed", "closed")]:
        v = d[key][~np.isnan(d[key])]
        print(f"  {label:<6} {loop:<7} p50={np.median(v):6.2f}s  "
              f"p95={np.percentile(v, 95):6.2f}s  p99={np.percentile(v, 99):6.2f}s")


# --- third figure: latency delta, fixed size vs. scaled out --------------------
# 2x2, all four panels on the same axes: top row is the fixed-size run of each
# system, bottom row the run that adds workers mid-trace, so a column is one
# system with and without the scale-out. Zoomed to ZOOM minutes because the
# scale-out lasts ~12 s and is invisible over the full 30 min trace.
if _args.a_scaling and _args.b_scaling:
    Z0, Z1 = _args.zoom
    EVENT_C = "#2563eb"

    # the same trim window as the main figure, so x means the same thing there
    A_sc = trim(load(_args.a_scaling, A_CLOSED), T0, T1)
    B_sc = trim(load(_args.b_scaling, B_CLOSED), T0, T1)
    grid = [[(A, f"{LABEL_A} - fixed cluster"), (B, f"{LABEL_B} - fixed cluster")],
            [(A_sc, f"{LABEL_A} - elastic cluster"), (B_sc, f"{LABEL_B} - elastic cluster")]]

    def zoomed(d):
        """Matched deltas inside the zoom window, on the trimmed-plot clock."""
        m = (~np.isnan(d["delta"])) & (d["x"] >= Z0) & (d["x"] <= Z1)
        return d["x"][m], d["delta"][m]

    # scale-out seconds are on the raw run clock; the plots are re-zeroed at T0
    events = [(t / 60.0 - T0, n) for t, n in _args.scale_events]
    # the events are cumulative totals, so the run started one node below the first
    n_from = min(n for _, n in _args.scale_events) - 1
    n_to = max(n for _, n in _args.scale_events)
    # only the last event gets a line, so the label carries how long the whole
    # ramp took: 843 s -> 855 s is 12 s, too short to resolve at this zoom
    span_s = max(t for t, _ in _args.scale_events) - min(t for t, _ in _args.scale_events)

    # one color scale over everything drawn in this figure
    zd = np.concatenate([zoomed(d)[1] for row in grid for d, _ in row])
    znorm = Normalize(vmin=float(zd.min()), vmax=float(zd.max()))

    figs, axs = plt.subplots(2, 2, figsize=(20, 9.5), sharex=True, sharey=True,
                             layout="constrained")
    for r, row in enumerate(grid):
        for c, (d, label) in enumerate(row):
            ax = axs[r, c]
            dx, dv = zoomed(d)
            bar_w = (Z1 - Z0) / max(len(dx), 1) * 1.5
            ax.bar(dx, dv, width=bar_w, color=DELTA_CMAP(znorm(dv)), zorder=2)
            ax.axhline(0, color="#333333", lw=1)

            # the fixed-size runs get the same marker, unlabelled and faint, only
            # as a time reference: no workers are added in those runs
            second_axis = ax.twinx()
            second_axis.set_ylim(0, 10)
            event_color = "#9ca3af"
            if r and events:
                # event_color = EVENT_C
                events_x, events_y = zip(*events)
                events_x = list(events_x)
                events_y = list(events_y)
                events_x.append(T1)
                events_y.append(events_y[-1])
                second_axis.step(events_x, events_y, where='post', color=event_color, linewidth=3, label='# Worker Nodes')
            else:
               second_axis.axhline(y=6, color=event_color, linewidth=3) 
            if c:
                second_axis.set_ylabel("# Worker Nodes", color=event_color)
            else:
                second_axis.yaxis.set_ticklabels([])

            second_axis.tick_params(axis='y', colors=event_color)
            ax.set_title(label, pad=10)
            ax.grid(True, axis="y", alpha=0.25)
            for s in ("top", "right"):
                ax.spines[s].set_visible(False)

    for ax in axs[1, :]:
        ax.set_xlabel("Arrival time (min)")
        ax.set_xlim(Z0, Z1)
        ax.xaxis.set_major_locator(MultipleLocator(1))
    for ax in axs[:, 0]:
        ax.set_ylabel("Latency delta (s)\nopen-closed loop")

    cax = axs[0, 1].inset_axes([0.52, 0.86, 0.42, 0.05])
    cbz = figs.colorbar(ScalarMappable(norm=znorm, cmap=DELTA_CMAP), cax=cax,
                        orientation="horizontal")
    cbz.set_label("delta (s)", fontsize=18, labelpad=2)
    cbz.ax.tick_params(labelsize=15, pad=1)
    cbz.outline.set_linewidth(0.6)

    scale_out = str(_out.with_name(_out.stem + "_scaling_delta" + _out.suffix))
    figs.savefig(scale_out, dpi=150)
    print(f"saved {scale_out}  (zoom {Z0:.1f}-{Z1:.1f} min of the trimmed plot "
          f"= {T0 + Z0:.1f}-{T0 + Z1:.1f} min of the raw trace)")
    for t, n in _args.scale_events:
        print(f"  scale-out at {t:.0f}s raw = {t / 60.0 - T0:.2f} min plotted "
              f"-> {n} nodes")
    for row in grid:
        for d, label in row:
            v = zoomed(d)[1]
            print(f"  {label:<18} n={len(v):3d}  median delta={np.median(v):+7.2f}s  "
                  f"p95={np.percentile(v, 95):+7.2f}s  max={v.max():+7.2f}s")
