import pandas as pd
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

def parse_measurements(env, file_path):
    rows = []

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or ':' not in line:
                continue

            label_part, timings_part = line.split(':', 1)
            query_name = label_part.replace('Query ', '').strip()
            query_name = query_name.replace("TPCH_Q", "q")
            timings = [float(t) for t in timings_part.strip().split(',')]

            # Create a row for every single timing (Long Format)
            for t in timings:
                rows.append({'Environment': env, 'Query': query_name, 'Latency (ms)': t, 'Latency (s)': (t/1000)})

    return pd.DataFrame(rows)


def selected_queries_plot(data_dict):
    """Grouped bars showing the mean latency, with errorbars spanning min/max.

    Bars are drawn with matplotlib directly (instead of sns.barplot) because the
    installed seaborn does not support custom errorbar functions.
    """
    df = pd.concat([parse_measurements(env, path) for path, env in data_dict["data"]])

    queries = data_dict["queries"]
    df = df[df['Query'].isin(queries)]

    environments = [env for _, env in data_dict["data"]]
    palette = data_dict["col_palette"]
    hatches = data_dict.get("hatches", [''] * len(environments))

    stats = df.groupby(['Environment', 'Query'])['Latency (ms)'].agg(['mean', 'min', 'max'])

    n_env = len(environments)
    x = range(len(queries))
    total_width = 0.9
    bar_width = total_width / n_env

    f, ax = plt.subplots(figsize=(data_dict["fig_width"], data_dict["fig_height"]))
    # light gray dashed y gridlines behind the bars
    ax.yaxis.grid(True, color="lightgray", linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)

    for i, env in enumerate(environments):
        offset = -total_width / 2 + bar_width * (i + 0.5)
        means = [stats.loc[(env, q), 'mean'] for q in queries]
        lower = [stats.loc[(env, q), 'mean'] - stats.loc[(env, q), 'min'] for q in queries]
        upper = [stats.loc[(env, q), 'max'] - stats.loc[(env, q), 'mean'] for q in queries]
        # errorbars in a darker variant of the bar color
        ax.bar([xi + offset for xi in x], means, bar_width, label=env, color=palette[i],
               hatch=hatches[i], edgecolor=adjust_hex_lightness(palette[i], 0.7), linewidth=0.6,
               yerr=[lower, upper], capsize=2,
               error_kw={'ecolor': adjust_hex_lightness(palette[i], 0.5), 'elinewidth': 1, 'capthick': 1})

    ax.set_xticks(list(x))
    ax.set_xticklabels(queries)
    # drop the default x margins so the bars sit close to the axes frame
    ax.set_xlim(-0.5, len(queries) - 0.5)
    ax.margins(y=0.02)
    ax.tick_params(axis='both', pad=1.5, length=2)
    ax.set_ylabel('Latency [ms]', labelpad=2)
    # ax.set_title(data_dict["title"])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=data_dict["label_cols"],
              frameon=False, handlelength=1, handleheight=1,
              borderpad=0, borderaxespad=0, labelspacing=0.3,
              handletextpad=0.4, columnspacing=1.0)
    plt.tight_layout(pad=0.15)
    # plt.show()
    plt.savefig(data_dict["out_path"], bbox_inches="tight", pad_inches=0.01)
    plt.close(f)


SELECTED_QUERIES = ['q2', 'q6']

FULL_SF10_DC = {
    "data": [("data/cluster-vs-s3-data/plume-dc.txt", "Plume (cluster data)"),
             ("data/cluster-vs-s3-data/plume-s3.txt", "Plume (s3 data)"),
             ("data/cluster-vs-s3-data/duckdb-dc.txt", "DuckDB (cluster data)"),
             ("data/cluster-vs-s3-data/duckdb-s3.txt", "DuckDB (s3 data)")],
    "col_palette": [adjust_hex_lightness(COL_DANDELION, 1.15),
                    adjust_hex_lightness(COL_DANDELION, 0.85),
                    adjust_hex_lightness(COL_DUCKDB, 1.15),
                    adjust_hex_lightness(COL_DUCKDB, 0.85)],
    "hatches": ['', '///', '', '///'],
    "queries": SELECTED_QUERIES,
    "title": "TPC-H Latencies (c5n.metal, sf=10)",
    "out_path": "plots/e2e_dc_sf10_full.pdf",
    "fig_width": 5,
    "fig_height": 2.4,
    "label_cols": 2,
}

DUCKDB_SF10_DC = {
    "data": [("data/cluster-vs-s3-data/duckdb-dc.txt", "fetching cluster data"),
             ("data/cluster-vs-s3-data/duckdb-s3.txt", "fetching s3 data")],
    "col_palette": [adjust_hex_lightness(COL_DUCKDB, 1.15),
                    adjust_hex_lightness(COL_DUCKDB, 0.85)],
    "hatches": ['', '///'],
    "queries": SELECTED_QUERIES,
    "title": "TPC-H Latencies (c5n.metal, sf=10, DuckDB)",
    "out_path": "plots/e2e_dc_sf10_duckdb.pdf",
    "fig_width": 5,
    "fig_height": 2.2,
    "label_cols": 2,
}


selected_queries_plot(FULL_SF10_DC)
selected_queries_plot(DUCKDB_SF10_DC)
