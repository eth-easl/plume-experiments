"""
Compact raw per-query timings into an aggregated CSV.

Usage:
    python compact_results.py <data-file> <output-csv> <scale-factor>
"""

import argparse
import os
import re
import pandas as pd

COLUMNS = ["query_number", "scale", "Min", "Mean", "Max"]
QUERY_LINE = re.compile(r"^\s*Query\s+\S*?q(\d+)\s*:\s*(.+?)\s*$")

def parse_data_file(path):
    timings = {}
    with open(path) as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            match = QUERY_LINE.match(line)
            if match is None:
                raise ValueError(f"{path}:{line_number}: unexpected line: {line.strip()}")
            query_number = int(match.group(1))
            values = [float(v) for v in match.group(2).split(",") if v.strip()]
            if not values:
                raise ValueError(f"{path}:{line_number}: no timings for query {query_number}")
            timings[query_number] = values
    if not timings:
        raise ValueError(f"{path}: no query timings found")
    return timings


def aggregate(timings, scale):
    rows = [
        {
            "query_number": query_number,
            "scale": scale,
            "Min": min(values),
            "Mean": sum(values) / len(values),
            "Max": max(values),
        }
        for query_number, values in sorted(timings.items())
    ]
    return pd.DataFrame(rows, columns=COLUMNS)


def load_output(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    missing = [col for col in COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing column(s): {', '.join(missing)}")
    return df


def merge(existing, new):
    if existing.empty:
        return new.copy()

    merged = existing.copy()
    key = list(zip(merged["query_number"], merged["scale"]))
    appended = []
    for _, row in new.iterrows():
        try:
            index = key.index((row["query_number"], row["scale"]))
        except ValueError:
            appended.append(row)
            continue
        for col in ("Min", "Mean", "Max"):
            merged.iloc[index, merged.columns.get_loc(col)] = row[col]

    if appended:
        merged = pd.concat([merged, pd.DataFrame(appended, columns=COLUMNS)], ignore_index=True)
    return merged


def write_output(df, path):
    df = df.copy()
    df["query_number"] = df["query_number"].astype(int)
    df["scale"] = df["scale"].astype(int)
    for col in ("Min", "Max"):
        values = pd.to_numeric(df[col])
        df[col] = values.astype(int) if (values % 1 == 0).all() else values.round(1)
    df["Mean"] = pd.to_numeric(df["Mean"]).round(1)
    df.to_csv(path, index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_file", help="raw timings file (see tmp/ for examples)")
    parser.add_argument("output_file", help="aggregated CSV to create or update")
    parser.add_argument("scale", type=int, help="scale factor of the run, e.g. 1, 10, 100")
    args = parser.parse_args()

    timings = parse_data_file(args.data_file)
    new = aggregate(timings, args.scale)
    merged = merge(load_output(args.output_file), new)
    write_output(merged, args.output_file)

    print(f"Wrote {len(new)} queries at scale {args.scale} to {args.output_file} "
          f"({len(merged)} rows total)")


if __name__ == "__main__":
    main()
