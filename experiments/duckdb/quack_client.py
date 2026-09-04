import argparse
import duckdb
import json
import os
import time

parser = argparse.ArgumentParser(description="Runs an instance of DuckDB that acts as the server using the quack protocol.")
parser.add_argument("server_ip", type=str)
parser.add_argument("config", type=str)
parser.add_argument("-s", "--secret", type=str, default="quack_secret")
args = parser.parse_args()

def create_table_map(config):
    table_path_prefix = os.path.expanduser(config["tablePathPrefix"]) if "tablePathPrefix" in config else ""
    table_path_suffix = config["tablePathSuffix"] if "tablePathSuffix" in config else ""
    map = {}
    for table in ["customer", "lineitem", "nation", "orders", "part", "partsupp", "region", "supplier"]:
        if "tableNumFiles" in config and table in config["tableNumFiles"]:
            num_files = config["tableNumFiles"][table]
            path = "read_parquet(["
            for i in range(num_files):
                path += f"'{table_path_prefix}/{table}/{table}.{i+1}{table_path_suffix}'"
                if i < num_files-1:
                    path += ", "
            path += "])"
            map[f"[{table}]"] = path
        else:
            map[f"[{table}]"] = f"'{table_path_prefix}/{table}/{table}{table_path_suffix}'"
    return map

with open(args.config, "r") as file:
    config = json.load(file)

con = duckdb.connect()
con.execute(f"""
FORCE INSTALL httpfs; 
FORCE INSTALl quack;

LOAD httpfs;
LOAD quack;

CREATE SECRET (
    TYPE quack,
    TOKEN '{args.secret}'
);
ATTACH 'quack:{args.server_ip}' AS remote (
    DISABLE_SSL true
);
""")

table_map = create_table_map(config)

timings = {}
for query in config["queries"]:
    timings[query] = []
    
for _ in range(config["repetitions"]):
    for qry_idx, query in enumerate(config["queries"]):
        print(f"Running query {query}")

        storage_prefix = os.path.expanduser(config["queryStoragePrefix"])
        with open(f"{storage_prefix}{query}", "r") as file:
            sql = file.read()
        
        for placeholder, table_path in table_map.items():
            sql = sql.replace(placeholder, table_path)

        start_time = time.time()
        res = con.sql(f"FROM remote.query(\"{sql}\");")
        end_time = time.time()
        timings[query].append(end_time - start_time)

        if config["debugPrints"]:
            res.show()
        
for query, measurements in timings.items():
    out = f"Query {query.split('.')[0].lower()}: "
    for m in measurements:
        out += f"{int(m*1000)},"
    out = out[:-1]
    print(out)

con.close()
