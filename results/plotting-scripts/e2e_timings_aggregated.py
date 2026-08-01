import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import colorsys

COL_DANDELION = "#17f565"
COL_DUCKDB = "#ea7c45"
COL_TRINO = "#306ee9"
COL_ATHENA = "#f343b0"
COL_BIGQUERY = "#a847f3"

def adjust_lightness(color, amount):
    """
    Adjusts the lightness of a given RGB color.
    
    :param color: A tuple of (R, G, B) integers from 0 to 255.
    :param amount: Float. > 1 to lighten, < 1 to darken (e.g., 1.2 is 20% lighter, 0.8 is 20% darker).
    :return: A tuple of (R, G, B) integers representing the new shade.
    """
    r, g, b = [x / 255.0 for x in color]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    new_l = max(0, min(1, l * amount))
    new_r, new_g, new_b = colorsys.hls_to_rgb(h, new_l, s)
    return (int(new_r * 255), int(new_g * 255), int(new_b * 255))

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = ''.join(char * 2 for char in hex_str)
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb_tuple):
    return '#{:02x}{:02x}{:02x}'.format(*rgb_tuple)

def adjust_hex_lightness(hex_str, amount):
    rgb = hex_to_rgb(hex_str)
    new_rgb = adjust_lightness(rgb, amount)
    return rgb_to_hex(new_rgb)

def draw_bar_break(ax, bar, y, color):
    """Draw a diagonal 'break' symbol across the top of a clipped bar."""
    x0, x1 = bar.get_x(), bar.get_x() + bar.get_width()
    dy = 0.012 * (ax.get_ylim()[1] - ax.get_ylim()[0])
    # white gap to visually cut the bar, then two parallel slashes
    ax.add_patch(plt.Rectangle((x0, y - dy), x1 - x0, 2 * dy,
                               color="white", zorder=3, clip_on=False))
    line_kw = dict(color=color, lw=0.8, zorder=4, clip_on=False, solid_capstyle="round")
    ax.plot([x0, x1], [y - 1.5 * dy, y - 0.5 * dy], **line_kw)
    ax.plot([x0, x1], [y + 0.5 * dy, y + 1.5 * dy], **line_kw)


def read_results(file_path, env):
    rows = []
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("query_number"):
                continue
            
            values = line.split(',')
            assert len(values) == 5
            scale = int(values[1])

            query_name = f"q{values[0]}"
            latency_min = float(values[2])
            latency_mean = float(values[3])
            latency_max = float(values[4])
            rows.append({'Environment': env, 'Query': query_name, 'Scalefactor': scale, 
                         'Latency mean (ms)': latency_mean, 'Latency mean (s)': (latency_mean/1000), 
                         'Latency min (ms)': latency_min, 'Latency min (s)': (latency_min/1000),
                         'Latency max (ms)': latency_max, 'Latency max (s)': (latency_max/1000)})
    
    return pd.DataFrame(rows)


def plot(data_dict, valid_queries=None):
    dfs = []
    for data in data_dict["data"]:
        dfs.append(read_results(data[0], data[1]))
    df = pd.concat(dfs)

    if valid_queries is None:
        valid_queries = [f'q{i}' for i in range(1, 23)]
    df = df[df['Query'].isin(valid_queries)]
    df = df[df['Environment'].isin(data_dict['envs'])]
    ordered_names = sorted(df['Query'].unique(), key=lambda x: int(x[1:]))

    fig = plt.figure(figsize=(data_dict["fig_width"], data_dict["fig_height"]))
    gs = fig.add_gridspec(len(data_dict['sf']), 1, hspace=0.2)
    for i, sf in enumerate(data_dict['sf']):
        df_sf = df[df['Scalefactor'] == sf]
        ax = fig.add_subplot(gs[i])
        pivot_mean = df_sf.pivot(index="Query", columns="Environment", values=f"Latency mean ({data_dict['y_scale']})").reindex(index=ordered_names, columns=data_dict['envs'])
        pivot_min = df_sf.pivot(index="Query", columns="Environment", values=f"Latency min ({data_dict['y_scale']})").reindex(index=ordered_names, columns=data_dict['envs'])
        pivot_max = df_sf.pivot(index="Query", columns="Environment", values=f"Latency max ({data_dict['y_scale']})").reindex(index=ordered_names, columns=data_dict['envs'])
        yerr_lower = pivot_mean - pivot_min
        yerr_upper = pivot_max - pivot_mean
        pivot_mean.plot(
            ax=ax,
            kind="bar",
            rot=0,
            width=0.7,
            color=data_dict['colors'],
            # edgecolor="black",  # Optional: adds crisp borders around bars
            # linewidth=0.4,
        )
        ax.margins(x=0.005)
        # light gray dashed y gridlines behind the bars
        ax.yaxis.grid(True, color="lightgray", linestyle="--", linewidth=0.7)
        ax.set_axisbelow(True)

        # find a cap so a few dominating bars don't squash the rest:
        # anything taller than break_factor * the typical bar (median) is an outlier
        tops = (pivot_mean + yerr_upper).values.flatten()
        tops = tops[~np.isnan(tops)]
        break_factor = data_dict.get("break_factor", 4)
        reference = np.median(tops)
        inliers = tops[tops <= break_factor * reference]
        cap = None
        if inliers.size and inliers.max() < tops.max():
            cap = 1.06 * inliers.max()
            x_top_lim = cap * 1.2
            ax.set_ylim(top=x_top_lim)  # headroom for the value labels

        # draw error bars per series in a darker variant of the bar color;
        # clip bars above the cap and label their true value instead
        for container, env, base_color in zip(ax.containers, pivot_mean.columns, data_dict['colors']):
            dark = adjust_hex_lightness(base_color, 0.5)
            for j, bar in enumerate(container):
                h = bar.get_height()
                if np.isnan(h):
                    continue
                xc = bar.get_x() + bar.get_width() / 2
                if cap is not None and h > x_top_lim:
                    bar.set_height(cap)
                    draw_bar_break(ax, bar, cap * 0.94, dark)
                    ax.annotate(f"{h:.0f}", (xc, cap), xytext=(0, 2),
                                textcoords="offset points", ha="center", va="bottom",
                                fontsize=7, rotation=90, color=dark)
                else:
                    lo = yerr_lower[env].values[j]
                    hi = yerr_upper[env].values[j]
                    ax.errorbar(xc, h, yerr=[[lo], [hi]], fmt="none",
                                ecolor=dark, elinewidth=1, capsize=2, capthick=1)
        ax.text(0.01, 0.83, f"sf={sf}", transform=ax.transAxes, fontsize=11, fontstyle='italic',
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.8, edgecolor="none"))
        handles, labels = ax.get_legend_handles_labels()
        ax.set_xlabel("")
        ax.get_legend().remove()
    
    # single legend below the last subplot, no frame
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.18),
              ncol=data_dict["label_cols"], frameon=False, handlelength=1, handleheight=1)

    top_adjust = 0.98 if len(data_dict['sf']) == 1 else 0.99
    bot_adjust = 0.25 if len(data_dict['sf']) == 1 else 0.13
    if 'title' in data_dict:
        fig.suptitle(data_dict["title"])
        top_adjust = 0.94 if len(data_dict['sf']) == 1 else 0.8
    fig.subplots_adjust(left=0.05, right=0.98, top=top_adjust, bottom=bot_adjust)
    # plt.show()
    plt.savefig(data_dict["out_path"])


SINGLE_NODE = {
    "data": [("data/single-query/plume-1w-aggregated.csv", "Plume"),
             ("data/single-query/duckdb-aggregated.csv", "DuckDB"),
             ("data/single-query/trino-1w-aggregated.csv", "Trino"),
             ("data/single-query/athena-aggregated.csv", "Athena"),
             ("data/single-query/big-query-aggregated.csv", "Big Query")],
    "colors": [adjust_hex_lightness(COL_DANDELION, 0.85),
               adjust_hex_lightness(COL_DUCKDB, 1), 
               adjust_hex_lightness(COL_TRINO, 0.85), 
               adjust_hex_lightness(COL_ATHENA, 1), 
               adjust_hex_lightness(COL_BIGQUERY, 1)],
    "envs": ["Plume", "DuckDB", "Trino", "Athena", "Big Query"],
    "sf": [1, 10],
    "y_scale": "s",
    # "title": "TPC-H Latencies",
    "out_path": "plots/e2e_1worker.pdf",
    "fig_width": 11,
    "fig_height": 4.5,
    "label_cols": 5,
    "break_factor": 3,
}

EC2_6W = {
    "data": [("data/single-query/plume-6w-aggregated.csv", "Plume"),
             ("data/single-query/trino-6w-aggregated.csv", "Trino"),
             ("data/single-query/athena-aggregated.csv", "Athena"),
             ("data/single-query/big-query-aggregated.csv", "Big Query")],
    "colors": [adjust_hex_lightness(COL_DANDELION, 0.85),
               adjust_hex_lightness(COL_TRINO, 0.85), 
               adjust_hex_lightness(COL_ATHENA, 1), 
               adjust_hex_lightness(COL_BIGQUERY, 1)],
    "envs": ["Plume", "Trino", "Athena", "Big Query"],
    "sf": [100],
    "y_scale": "s",
    # "title": "TPC-H Latencies",
    "out_path": "plots/e2e_6workers.pdf",
    "fig_width": 11,
    "fig_height": 2.5,
    "label_cols": 5,
    "break_factor": 2.5,
}

MOTIVATION_ALL = {
    "data": [("data/single-query/duckdb-aggregated.csv", "DuckDB"),
             ("data/single-query/trino-1w-aggregated.csv", "Trino (1 worker)"),
             ("data/single-query/trino-6w-aggregated.csv", "Trino (6 workers)")],
    "colors": [adjust_hex_lightness(COL_DUCKDB, 1),
               adjust_hex_lightness(COL_TRINO, 0.85), 
               adjust_hex_lightness(COL_TRINO, 1.3)],
    "envs": ["DuckDB", "Trino (1 worker)", "Trino (6 workers)"],
    "sf": [1, 10, 100],
    "y_scale": "s",
    # "title": "TPC-H Latencies",
    "out_path": "plots/e2e_motivation_all.pdf",
    "fig_width": 11,
    "fig_height": 6.5,
    "label_cols": 5,
    "break_factor": 3,
}

MOTIVATION = {
    "data": [("data/single-query/duckdb-aggregated.csv", "DuckDB"),
             ("data/single-query/trino-1w-aggregated.csv", "Trino (1 worker)"),
             ("data/single-query/trino-6w-aggregated.csv", "Trino (6 workers)")],
    "colors": [adjust_hex_lightness(COL_DUCKDB, 1),
               adjust_hex_lightness(COL_TRINO, 0.85), 
               adjust_hex_lightness(COL_TRINO, 1.3)],
    "envs": ["DuckDB", "Trino (1 worker)", "Trino (6 workers)"],
    "sf": [1, 10, 100],
    "y_scale": "s",
    # "title": "TPC-H Latencies",
    "out_path": "plots/e2e_motivation.pdf",
    "fig_width": 6,
    "fig_height": 6.5,
    "label_cols": 5,
    "break_factor": 4,
}

plot(SINGLE_NODE)
plot(EC2_6W)
plot(MOTIVATION_ALL, )
plot(MOTIVATION, ['q1', 'q12', 'q22'])

