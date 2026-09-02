# DuckDB Experiment Utilities

## Quack Benchmarking

Together the `quack_client.py` and `quack_server.py` scripts run TPC-H benchmark queries over the [Quack](https://github.com/duckdb/duckdb-quack) protocol using DuckDB. The server exposes a DuckDB instance over the network; the client connects to it, executes queries, and reports per-query timings.

### Server

Starts a DuckDB instance that listens for incoming Quack connections.

```bash
python quack_server.py <hostname> [-s <secret>]
```

| Argument | Description |
|---|---|
| `hostname` | Address to serve on (e.g. `0.0.0.0:1234`) |
| `-s`, `--secret` | Authentication token (default: `quack_secret`) |

The server runs until stopped with `Ctrl+C`.

### Client

Connects to a running server, loads SQL queries from disk, substitutes table paths, and runs each query the configured number of times.

```bash
python quack_client.py <server_ip> <config> [-s <secret>]
```

| Argument | Description |
|---|---|
| `server_ip` | Address of the running server (e.g. `0.0.0.0:1234`) |
| `config` | Path to a JSON config file |
| `-s`, `--secret` | Authentication token (must match server, default: `quack_secret`) |

**Config file fields:**

| Field | Description |
|---|---|
| `queries` | List of query filenames to run |
| `queryStoragePrefix` | Directory prefix for query files |
| `repetitions` | Number of times to run each query |
| `tablePathPrefix` | Path prefix for TPC-H table files |
| `tablePathSuffix` | File suffix for table files (e.g. `.parquet`) |
| `tableNumFiles` | (Optional) Map of table name → number of part files |
| `debugPrints` | Print query results to stdout if `true` |

Table names in SQL files are substituted using bracket placeholders: `[lineitem]`, `[orders]`, etc.

Timing output is printed per query at the end:

```
Query TPCH_Q1: 412,398,401
Query TPCH_Q6: 88,91,90
```
