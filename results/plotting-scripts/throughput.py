import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import colorsys

COL_DANDELION = "#17f565"
COL_DUCKDB = "#ea7c45"
COL_TRINO = "#306ee9"
COL_ATHENA = "#f343b0"
COL_BIGQUERY = "#a847f3"

INTERVAL_PLUME_S = 60
INTERVAL_TRINO_S = 120
TIMEOUT_MS = 10000
Y_TICKS = [0, 2.5, 5, 7.5, 10, 12.5]
# Manual axes margins in figure fractions. tight_layout keeps a ~0.05in pad on
# every side, which shows up as a white border in the paper; these hug the axis
# decorations instead. Override per figure with a "margins" key.
MARGINS = {"left": 0.134, "right": 0.995, "top": 0.99, "bottom": 0.193}

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

def pad_timeouts(df, interval_s):
    """
    Every (System, Query, RPS) window should contain RPS * INTERVAL_S requests.
    Requests that never came back are counted as timeouts, so pad each window up
    to its expected size with TIMEOUT_MS entries.

    Grouping (rather than tracking the current window while scanning the file)
    keeps this correct even when the input is not ordered by RPS -- the Trino
    CSVs are not.
    """
    padding = []

    for (system, query, rps), group in df.groupby(['System', 'Query', 'RPS']):
        expected = int(rps * interval_s)
        missing = expected - len(group)
        if missing < 0:
            print(f"{system} {query} @ {rps} rps: got {len(group)} while only {expected} were expected")
        elif missing > 0:
            print(f"{system} {query} @ {rps} rps: adding {missing} missing values")
            padding.extend(missing * [{
                'System': system, 'Query': query, 'RPS': rps,
                'Latency (ms)': TIMEOUT_MS, 'Latency (s)': (TIMEOUT_MS/1000),
            }])

    if not padding:
        return df
    return pd.concat([df, pd.DataFrame(padding)], ignore_index=True)

def parse_plume_measurements(file_path, interval_s):
    rows = []

    with open(file_path, 'r') as f:
        query_name = ""
        for line in f:
            if line.startswith("Query"):
                query_name = line.replace('Query ', '').strip()[:-1]
                continue

            line = line.strip()
            if not line or ':' not in line:
                continue

            rps_raw, timings_part = line.split(':', 1)
            rps = float(rps_raw)

            for t in [float(t) for t in timings_part.strip().split(',')]:
                rows.append({'System': 'Plume', 'Query': query_name, 'RPS': rps, 'Latency (ms)': t, 'Latency (s)': (t/1000)})

    return pad_timeouts(pd.DataFrame(rows), interval_s)

def parse_trino_measurements(file_path, query_name, interval_s):
    rows = []

    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith(","):
                continue

            line = line.strip()
            if not line:
                continue

            _, rps_raw, latency_raw = line.split(',')
            rps = float(rps_raw)
            latency = float(latency_raw)
            rows.append({'System': 'Trino', 'Query': query_name, 'RPS': rps, 'Latency (ms)': latency, 'Latency (s)': (latency/1000)})

    return pad_timeouts(pd.DataFrame(rows), interval_s)

def align_rps(df_plume, df_trino):
    """
    Drop Trino RPS levels that Plume was not measured at. Plume is kept in full,
    so its curve still extends past the last shared level.
    """
    plume_rps = set(df_plume['RPS'].unique())
    trino_rps = set(df_trino['RPS'].unique())

    missing_trino = sorted(plume_rps - trino_rps)
    if missing_trino:
        print(f"WARNING: no Trino measurements at {len(missing_trino)} Plume RPS level(s): {missing_trino}")

    dropped_trino = sorted(trino_rps - plume_rps)
    if dropped_trino:
        print(f"Dropping {len(dropped_trino)} Trino-only RPS level(s) in [{dropped_trino[0]}, {dropped_trino[-1]}]")

    return df_plume, df_trino[df_trino['RPS'].isin(plume_rps)]

def single_plot(data_dict):
    print("Parsing plume")
    df_plume = parse_plume_measurements(data_dict["plume_data"][0], data_dict["plume_data"][1])
    print("Parsing trino")
    df_trino = parse_trino_measurements(data_dict["trino_data"][0], data_dict["trino_data"][1], data_dict["trino_data"][2])
    df_plume, df_trino = align_rps(df_plume, df_trino)
    df = pd.concat([df_plume, df_trino], ignore_index=True)

    # Thresholds must be per system: Plume is uniformly faster than Trino, so a
    # threshold pooled over both systems keeps Trino rows only and Plume vanishes.
    # p50_threshold = df.groupby(['System', 'RPS'])['Latency (s)'].transform('quantile', 0.5)
    # p90_threshold = df.groupby(['System', 'RPS'])['Latency (s)'].transform('quantile', 0.9)
    p95_threshold = df.groupby(['System', 'RPS'])['Latency (s)'].transform('quantile', 0.95)
    # df_p50 = df[df['Latency (s)'] >= p50_threshold].copy()
    # df_p90 = df[df['Latency (s)'] >= p90_threshold].copy()
    df_p95 = df[df['Latency (s)'] >= p95_threshold].copy()
    # df_p50['Percentile'] = "p50"
    # df_p90['Percentile'] = "p90"
    # df_p95['Percentile'] = "p95"
    # combined_df = pd.concat([df_p50, df_p90, df_p95], ignore_index=True)

    f, ax = plt.subplots(figsize=(data_dict["fig_width"], data_dict["fig_height"]))
    sns.lineplot(
        data=df_p95, x='RPS', y='Latency (s)', hue='System',
        palette={'Plume': adjust_hex_lightness(COL_DANDELION, 0.85),
                 'Trino': adjust_hex_lightness(COL_TRINO, 0.85)},
        errorbar='sd', err_style='bars', err_kws={'capsize': 4},
        marker='o'
    )
    ax.set_ylabel("p95 Latency [s]")

    if 'timeout_s' in data_dict:
        timeout_s = data_dict['timeout_s']
        # No label: the timeout is annotated on the line itself, not in the legend.
        plt.axhline(y=timeout_s, color='red', linestyle='--', linewidth=1.5)
        # x in axes fractions, y in data coords, so the text sits just above the
        # line at its left end regardless of the RPS range.
        ax.text(0.98, timeout_s*1.03, f"timeout={timeout_s:g}s",
                transform=ax.get_yaxis_transform(),
                ha='right', va='bottom', color='red', fontsize=10)

    ax.set_yticks(Y_TICKS)
    ax.set_ylim(Y_TICKS[0], Y_TICKS[-1] * 1.1)

    # plt.title(data_dict["title"])
    handles, labels = ax.get_legend_handles_labels()
    systems = [(h, l) for h, l in zip(handles, labels) if l in ('Plume', 'Trino')]
    ax.legend(*zip(*systems), loc='upper left', ncol=2)
    f.subplots_adjust(**{**MARGINS, **data_dict.get("margins", {})})
    # plt.show()
    plt.savefig(data_dict["out_path"])



SINGLE_Q5_SF10 = {
    "plume_data": ("data/throughput/plume-6w-throughput-q5-90s.txt", 60),
    "trino_data": ("data/throughput/trino-6w-latency-q5-aggregated.csv", "q5", 60),
    "title": "TPC-H Query 5 Throughput (c5n.metal, sf=10)",
    "out_path": "plots/throughput_q5_sf10.pdf",
    "fig_width": 4.5, "fig_height": 2.25,
    "label_cols": 3,
    "timeout_s": 10,
}

SINGLE_Q6_SF1 = {
    "plume_data": ("data/throughput/plume-6w-throughput-q6-180s.txt", 60),
    "trino_data": ("data/throughput/trino-6w-latency-q6-aggregated.csv", "q6", 60),
    "title": "TPC-H Query 6 Throughput (c5n.metal, sf=1)",
    "out_path": "plots/throughput_q6_sf1.pdf",
    "fig_width": 4.5, "fig_height": 2.25,
    "label_cols": 3,
    "timeout_s": 10,
}

single_plot(SINGLE_Q5_SF10)
single_plot(SINGLE_Q6_SF1)
