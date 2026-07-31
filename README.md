# Trino Experiments

***HEAVILY OUT-OF-DATE: will be cleaned up in the coming days***

---

This repository contains a small Trino experiment stack:

- `doe-suite-config/` defines the DoE-Suite experiment that provisions and starts Trino.
- `queries/` contains the TPC-H SQL templates used by the loader.
- `trino-loader/` submits TPC-H queries to Trino and records Trino query stats.
- `plots/plot_trino_split_spans.py` extracts split spans from Jaeger and writes SVG/CSV analysis outputs.

## Prerequisites

Install the local tools used by this repo:

- Python `>=3.9,<3.11`, matching `doe-suite-config/pyproject.toml`.
- Poetry, for `doe-suite-config`.
- Rust and Cargo, for `trino-loader`.
- SSH access to the machines listed in the selected DoE-Suite inventory.
- SSH agent forwarding so remote machines can clone this private Git repository.

Initialize the DoE-Suite submodule after cloning:

```sh
git submodule update --init --recursive
```

Set the DoE-Suite project variables from the repository root:

```sh
export DOES_PROJECT_DIR="$PWD"
export DOES_PROJECT_ID_SUFFIX="<your-short-id>"
```

`doe-suite-config/group_vars/all/main.yml` builds the remote project id as `dataprocessing_<DOES_PROJECT_ID_SUFFIX>` and uses `/tmp/<project-id>` as the remote experiment folder.

## Set Up a Trino Cluster With DoE-Suite

The Trino suite is defined in `doe-suite-config/designs/trino.yml`. Set `host_types.worker.n` there to the number of Trino workers you want to use. The selected inventory must contain at least that many machines in the `worker` group. By default, the design creates one `master` host and one `worker` host.

Create or edit an inventory before running:

- `doe-suite-config/inventory/cloudlab.yml` has `master_01` and `worker_01` entries with CloudLab hostnames and private IPs.

The Trino configuration templates are in `doe-suite-config/roles/trino/tasks/`: `config.properties`, `node.properties`, `jvm.config`, and `catalog/s3data.properties`. The role renders these into the remote Trino `etc/` directory on both master and worker hosts.

Configure Trino's filesystem cache in `doe-suite-config/roles/trino/tasks/catalog/s3data.properties`. The relevant settings are `fs.cache.enabled`, `fs.cache.directories`, and `fs.cache.max-sizes`; switch the cache directory between `/tmp/trino-cache` and `/dev/shm/trino-cache` depending on whether you want disk-backed or memory-backed cache.

The same `s3data.properties` file also contains the S3 and Glue catalog settings. Add the AWS S3 access key and secret key there before running against private TPC-H data.

The `setup-master` role also installs Prometheus, Grafana, and Jaeger. `setup-base` installs `prometheus-node-exporter` on every host. Trino OpenTelemetry tracing is enabled by default in `doe-suite-config/group_vars/all/main.yml` and points to Jaeger's OTLP gRPC endpoint on the master.

Run the suite from the `doe-suite` submodule, selecting an inventory by filename without `.yml`:

```sh
cd doe-suite
make run suite=trino id=new cloud=cloudlab
```

After setup, connect to the master services directly or through SSH port forwarding:

```sh
ssh -L 8080:localhost:8080 -L 9090:localhost:9090 -L 16686:localhost:16686 -L 3000:localhost:3000 <master-host>
```

With those forwards open, use these local service URLs:

- Trino coordinator: `http://localhost:8080`
- Prometheus: `http://localhost:9090`
- Jaeger: `http://localhost:16686`
- Grafana: `http://localhost:3000`

## Submit TPC-H Queries With trino-loader

`trino-loader` expects the TPC-H data to be available in Trino as:

```text
s3data.tpch_sf<SCALE_FACTOR>.<table>
```

The SQL files in `queries/q1.sql` through `queries/q22.sql` use templates like `` `DATASET.lineitem` ``. At runtime, `trino-loader` rewrites those references to `s3data.tpch_sf<SCALE_FACTOR>.lineitem`, strips the trailing semicolon, posts the statement to `/v1/statement`, follows `nextUri` until completion, and records the final Trino `stats` JSON.

Build the loader:

```sh
cd trino-loader
cargo build --release
cd ..
```

Run one query:

```sh
./trino-loader/target/release/trino-loader \
  --master <master-host-or-ip> \
  --port 8080 \
  --scale-factor 1 \
  --template-path queries \
  --query-number 1
```

## Analyze Split Spans

`plots/plot_trino_split_spans.py` is a standard-library Python script. It can either fetch live data from Trino, Jaeger, and Prometheus, or read saved JSON files.

With the SSH port forwards above open, run:

```sh
python3 plots/plot_trino_split_spans.py
```

The script defaults to Trino on `localhost:8080`, Jaeger on `localhost:16686`, and Prometheus on `localhost:9090`. It selects the latest traced non-failed Trino query unless `--query-id` is given. Outputs are written as `trino_split_spans_<queryId>.svg`, `trino_split_spans_<queryId>.csv`, `trino_child_spans_<queryId>.csv`, and `trino_stage_graph_<queryId>.svg`.

To analyze a downloaded Jaeger trace instead of fetching it live:

```sh
python3 plots/plot_trino_split_spans.py --trace-json <trace.json>
```
