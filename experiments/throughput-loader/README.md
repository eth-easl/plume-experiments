
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