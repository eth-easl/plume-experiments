import os.path as osp
import pandas as pd
import numpy as np
import colorsys
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

SHOW_LEGEND = True
SQUASH = True


HUES = np.linspace(130, 330, 8)
RESOURCE_HUE_MAP = {
    "customer": HUES[0],
    "lineitem": HUES[1],
    "nation": HUES[2],
    "orders": HUES[3],
    "part": HUES[4],
    "partsupp": HUES[5],
    "region": HUES[6],
    "supplier": HUES[7]
}

METHOD_PERC_MAP = {
    "HEAD": 20,
    "GET": 70,
    "POST": 70
}
METHOD_HATCH_MAP = {
    "HEAD": "//"
}

# light box drawn behind in-plot text so it stays readable on top of the bars
TEXT_BBOX = dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="none", alpha=0.9)

RUNTIME_FACE = "#E0E0E0"
RUNTIME_EDGE = "#909090"

def get_color(col_hue, percentage=50):
    h = col_hue / 360
    l = 0.35 + 0.5 * (percentage / 100)
    r, g, b = colorsys.hls_to_rgb(h, l, 0.85)
    return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"

def extract_timings(file_path):
    busy_until = []
    def find_slot(start, end):
        best_slot_idx = -1
        best_time_diff = -1
        for slot_idx, slot_end in enumerate(busy_until):
            time_diff = start - slot_end
            if time_diff > 0 and (best_time_diff == -1 or time_diff < best_time_diff):
                best_time_diff = time_diff
                best_slot_idx = slot_idx
        
        if best_slot_idx > -1:
            busy_until[best_slot_idx] = end
            return best_slot_idx
        else:
            busy_until.append(end)
            return len(busy_until)-1

    method = []
    resource = []
    start = []
    duration = []
    slot = []
    with open(file_path, 'r') as f:
        for line in f.readlines():
            if line.startswith('method'):
                continue

            parts = line.split(',')
            
            method.append(parts[0])

            r = osp.basename(parts[1])
            r_dot_idx = r.find('.')
            if r_dot_idx > 0:
                r = r[:r_dot_idx]
            resource.append(r)

            s = int(parts[2]) / 1000 # in ms
            d = int(parts[3]) / 1000 # in ms
            start.append(s)
            duration.append(d)
            slot.append(find_slot(s, s+d))

    df = pd.DataFrame({"method": method, "resource": resource, "start": start, 
                       "duration": duration, "slot": slot})
    df["start"] -= df["start"].min()
    return df

def query_runtime(file_path, query):
    """Mean end-to-end runtime [ms] of `query` (e.g. "q1") from a timings file."""
    with open(file_path, 'r') as f:
        for line in f:
            if ':' not in line:
                continue
            label_part, timings_part = line.split(':', 1)
            name = label_part.replace('Query ', '').strip().replace('TPCH_Q', 'q')
            if name == query:
                timings = [float(t) for t in timings_part.strip().split(',')]
                return sum(timings) / len(timings)
    return None

def axis_limits(*values):
    """x-limit and tick steps that fit `values` with just enough headroom for labels.

    Returns (max_time, major_step, minor_step). The limit is snapped to half a major
    step, so the longest bar always ends in the last ~10-15% of the axes.
    """
    needed = max(v for v in values if v) * 1.12
    exp = 10 ** np.floor(np.log10(needed / 6))
    major = next(m * exp for m in (1, 2, 2.5, 5, 10) if m * exp >= needed / 6)
    max_time = np.ceil(needed / (major / 2)) * (major / 2)
    return max_time, major, major / 5

def data_end(data):
    """Time [ms] at which the last data request of a trace completes."""
    return (data["start"] + data["duration"]).max()

def create_plot(ax, data, plotted_resources=None):
    for i, t in enumerate(data.itertuples()):
        y_val = i
        if SQUASH:
            y_val = t.slot
        
        facecol = get_color(RESOURCE_HUE_MAP.get(t.resource, 0), METHOD_PERC_MAP.get(t.method, 100))
        edgecol = get_color(RESOURCE_HUE_MAP.get(t.resource, 0), METHOD_PERC_MAP.get(t.method, 100) - 20)
        hatch = METHOD_HATCH_MAP.get(t.method, '')
        ax.barh(
            y=y_val, width=t.duration, left=t.start, height=1.0,
            align='center', color=facecol, edgecolor=edgecol, hatch=hatch
        )

        if plotted_resources is not None:
            plotted_resources[t.resource] = (facecol, edgecol)

    return int(data["slot"].max()) + 1 if SQUASH else len(data)

def add_runtime_lane(ax, runtime_ms, n_lanes, max_time, label=None):
    """Draw the total query runtime as a summary lane below the fetch traces.

    The trace timeline starts at the first data request, the runtime bar starts at
    the query start - the two are aligned at t=0, so the bar shows how much of the
    query is *not* covered by the fetch traces.
    """
    # the lane is sized relative to the trace area so it looks the same in every plot
    lane_h = max(1.0, 0.12 * n_lanes)
    gap = 0.45 * lane_h
    y = -0.5 - gap - lane_h / 2

    ax.barh(y=y, width=runtime_ms, left=0, height=lane_h, align='center',
            color=RUNTIME_FACE, edgecolor=RUNTIME_EDGE, zorder=2)
    ax.axvline(runtime_ms, color=RUNTIME_EDGE, linestyle='--', linewidth=0.8, zorder=1)
    ax.axhline(-0.5 - gap / 2, color="#BBBBBB", linewidth=0.8, zorder=1)

    if label is None:
        label = f"{runtime_ms:.0f} ms"
    # label past the right edge of the bar, unless it would run out of the axes
    if runtime_ms < 0.85 * max_time:
        ax.text(runtime_ms + 0.012 * max_time, y, label, va='center', ha='left',
                fontsize=8, color="#404040", zorder=3, bbox=TEXT_BBOX)
    else:
        ax.text(runtime_ms - 0.012 * max_time, y, label, va='center', ha='right',
                fontsize=8, color="#404040", zorder=3, bbox=TEXT_BBOX)

    ax.set_ylim(y - lane_h / 2 - 0.15 * lane_h, n_lanes - 0.45)

def single_plot(data_dict):
    data = extract_timings(data_dict["path"])

    fig, ax = plt.subplots(figsize=(6, 3))
    plotted_resources = dict()
    n_lanes = create_plot(ax, data, plotted_resources=plotted_resources)

    max_time, major_step, minor_step = axis_limits(data_end(data), data_dict.get("runtime"))
    if "plot_max_time" in data_dict:
        max_time = data_dict["plot_max_time"]
        major_step = data_dict["plot_major_step"]
        minor_step = data_dict["plot_minor_step"]

    major_ticks = np.arange(0, max_time+1, major_step)
    minor_ticks = np.arange(0, max_time, minor_step)
    ax.set_xticks(major_ticks)
    ax.set_xticks(minor_ticks, minor=True)
    ax.grid(which='both')
    ax.grid(which='minor', alpha=0.2)
    ax.grid(which='major', alpha=0.5)
    ax.yaxis.grid(False, which='both')
    ax.set_xlim([0, max_time])

    if data_dict.get("runtime"):
        add_runtime_lane(ax, data_dict["runtime"], n_lanes, max_time)

    ax.set_xlabel("Time [ms]", size=13)
    ax.set_ylabel("Functions", size=13)
    ax.set_yticks([])
    if "title" in data_dict and len(data_dict["title"]) > 0:
        ax.set_title(data_dict["title"], size=14)

    if SHOW_LEGEND:
        patches = []
        for r in RESOURCE_HUE_MAP.keys():
            if r in plotted_resources:
                fcol, ecol = plotted_resources[r]
                patches.append(mpatches.Patch(facecolor=fcol, edgecolor=ecol, linewidth=1, label=r))

        if "legend_pos" in data_dict:
            ax.legend(handles=patches, handlelength=1, handleheight=1, loc=data_dict["legend_pos"])
        else:
            ax.legend(handles=patches, handlelength=1, handleheight=1)

    plt.tight_layout()

    # plt.show()
    plt.savefig(data_dict["out_path"])
    plt.close()

def vertical_stacked_plot(data_dict):
    data_top = extract_timings(data_dict["path_top"])
    data_bot = extract_timings(data_dict["path_bot"])

    fig = plt.figure(figsize=(data_dict["fig_width"], data_dict["fig_height"]))
    gs = fig.add_gridspec(2, 1, hspace=0)
    ax_top = fig.add_subplot(gs[0])
    ax_bot = fig.add_subplot(gs[1])

    plotted_resources = dict()
    lanes_top = create_plot(ax_top, data_top, plotted_resources=plotted_resources)
    lanes_bot = create_plot(ax_bot, data_bot, plotted_resources=plotted_resources)

    max_time, major_step, minor_step = axis_limits(
        data_end(data_top), data_end(data_bot),
        data_dict.get("top_runtime"), data_dict.get("bot_runtime"))
    if "plot_max_time" in data_dict:
        max_time = data_dict["plot_max_time"]
        major_step = data_dict["plot_major_step"]
        minor_step = data_dict["plot_minor_step"]

    major_ticks = np.arange(0, max_time+1, major_step)
    minor_ticks = np.arange(0, max_time, minor_step)
    ax_bot.set_xticks(major_ticks)
    ax_bot.set_xticks(minor_ticks, minor=True)
    ax_bot.grid(which='both')
    ax_bot.grid(which='minor', alpha=0.2)
    ax_bot.grid(which='major', alpha=0.5)
    ax_bot.yaxis.grid(False, which='both')
    ax_bot.set_xlim([0, max_time])
    ax_top.set_xticks(major_ticks)
    ax_top.set_xticks(minor_ticks, minor=True)
    ax_top.grid(which='both')
    ax_top.grid(which='minor', alpha=0.2)
    ax_top.grid(which='major', alpha=0.5)
    ax_top.yaxis.grid(False, which='both')
    ax_top.set_xlim([0, max_time])

    if data_dict.get("top_runtime"):
        add_runtime_lane(ax_top, data_dict["top_runtime"], lanes_top, max_time)
    if data_dict.get("bot_runtime"):
        add_runtime_lane(ax_bot, data_dict["bot_runtime"], lanes_bot, max_time)

    ax_top.tick_params(axis='x', which='both', bottom=False, top=False, labelbottom=False)
    ax_top.set_yticks([])
    ax_bot.set_xlabel("Time [ms]")
    ax_bot.set_yticks([])

    ax_top.text(0.99, 0.95, data_dict["top_subtitle"], transform=ax_top.transAxes,
                fontsize=11, fontstyle='italic', va='top', ha='right', zorder=3, bbox=TEXT_BBOX)
    ax_bot.text(0.99, 0.95, data_dict["bot_subtitle"], transform=ax_bot.transAxes,
                fontsize=11, fontstyle='italic', va='top', ha='right', zorder=3, bbox=TEXT_BBOX)

    patches = []
    for r in RESOURCE_HUE_MAP.keys():
        if r in plotted_resources:
            fcol, ecol = plotted_resources[r]
            patches.append(mpatches.Patch(facecolor=fcol, edgecolor=ecol, linewidth=1, label=r))
    ax_bot.legend(handles=patches, loc="upper center", bbox_to_anchor=(0.5, -0.38),
                  ncol=len(patches), frameon=False, handlelength=1, handleheight=1)

    fig.subplots_adjust(bottom=0.26, top=0.95, left=0.06, right=0.97)

    # plt.show()
    plt.savefig(data_dict["out_path"])
    plt.close()


# stacked plots
# for sf in ["sf1", "sf10"]:
#     for q in ["q1", "q2", "q3", "q4", "q6", "q18", "q21"]:
for sf in ["sf10"]:
    for q in ["q1", "q2", "q3", "q4", "q6"]:
        rt_top = query_runtime(f"data/data-client-trace/runtimes/duckdb_dc.txt", q)
        rt_bot = query_runtime(f"data/data-client-trace/runtimes/plume_dc.txt", q)
        vertical_stacked_plot({
            "path_top": f"data/data-client-trace/duckdb_{q}_{sf}.txt",
            "path_bot": f"data/data-client-trace/plume_{q}_{sf}.txt",
            "top_subtitle": "DuckDB",
            "bot_subtitle": "Plume",
            "top_runtime": rt_top,
            "bot_runtime": rt_bot,
            "out_path": f"plots/dc_trace_{sf}_{q}.pdf",
            "fig_width": 5, "fig_height": 3
        })
        print(f"plots/dc_trace_{sf}_{q}.pdf")
