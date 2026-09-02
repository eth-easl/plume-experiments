import argparse
import duckdb
import time

parser = argparse.ArgumentParser(description="Runs an instance of DuckDB that acts as the server using the quack protocol.")
parser.add_argument("hostname", type=str)
parser.add_argument("-s", "--secret", type=str, default="quack_secret")
args = parser.parse_args()

con = duckdb.connect()
con.execute(f"""
SET enable_external_file_cache = false;
            
FORCE INSTALL httpfs; 
FORCE INSTALl quack; 

LOAD httpfs;
LOAD quack;

CALL quack_serve(
    'quack:{args.hostname}',
    token = '{args.secret}',
    allow_other_hostname => true
);
""")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping DuckDB server.")
finally:
    con.close()
