# Trace File Format (v2)

Binary, little-endian. Conventional file extension: `.plmt`.

## Compression

A file may be compressed as a whole. The compression is identified by an additional suffix on the file name:

| File name     | Compression |
|---------------|-------------|
| `*.plmt`      | none        |
| `*.plmt.gz`   | gzip        |
| `*.plmt.xz`   | xz          |

Everything below describes the uncompressed byte stream.

A file consists of a header followed by a sequence of tagged blocks until EOF.

## Primitives

| Type  | Encoding                                       |
|-------|------------------------------------------------|
| `u8`, `u16`, `u32`, `u64` | unsigned little-endian integers    |
| `str` | `u16` byte length, followed by that many UTF-8 bytes (no terminator) |

## Header

| Field      | Type          | Description                                  |
|------------|---------------|----------------------------------------------|
| magic      | 4 bytes       | ASCII `PLMT`                                 |
| version    | `u8`          | `2`                                          |
| n_ts       | `u8`          | number of timestamps per invocation          |
| ts_names   | `str` × n_ts  | timestamp names, in the order they appear in each record |

`n_ts` may be `0` only if no run in the file has timestamps.

## Blocks

Each block starts with a `u8` tag.

### `0x01` Query

| Field | Type  | Description |
|-------|-------|-------------|
| name  | `str` | query name  |

All run blocks that follow belong to this query, until the next query block. A query name may appear more than once; its runs are concatenated.

### `0x02` Run

| Field     | Type               | Description                                        |
|-----------|--------------------|----------------------------------------------------|
| flags     | `u8`               | which fields this run's records contain, see below |
| n_ids     | `u16`              | size of this run's id string table                 |
| ids       | `str` × n_ids      | invocation ids (e.g. `plume_stage`), referenced by index |
| n_records | `u32`              | number of invocation records                       |
| records   | record × n_records | see below                                          |

A run block must be preceded by a query block.

`flags` bits:

| Bit | Name       | Meaning when set |
|-----|------------|------------------|
| 0   | `HAS_TS`   | every record of this run contains `ts` |
| 1   | `HAS_DATA` | every record of this run contains `n_data` and `data` |
| 2   | `HAS_MEM`  | every record of this run contains `max_mem` |

At least one of `HAS_TS` and `HAS_DATA` must be set (`HAS_MEM` alone is not enough), and all other bits must be `0`. `HAS_TS` requires `n_ts > 0`. The flags apply to the whole run, so runs with and without timestamps, data or memory can be mixed in one file.

### Invocation record

Variable size: `12` bytes, plus `8` if `HAS_MEM`, plus `8 × n_ts` if `HAS_TS`, plus `2 + 12 × n_data` if `HAS_DATA`.

| Field      | Type               | Description |
|------------|--------------------|-------------|
| parent     | `u32`              | index of the parent record within this run, `0xFFFFFFFF` for a root |
| group      | `u16`              | index of the parent's child group this invocation belongs to (0 for roots) |
| id         | `u16`              | index into the run's id string table |
| node       | `u32`              | node id |
| max_mem    | `u64`              | only if `HAS_MEM`: maximum memory used by the invocation, in bytes; `0` = not recorded |
| ts         | `u64` × n_ts       | only if `HAS_TS`: timestamps in microseconds, relative to the start of the run; `0` = not recorded |
| n_data     | `u16`              | only if `HAS_DATA`: number of data entries of this invocation |
| data       | data entry × n_data | only if `HAS_DATA`: see below |

#### Data entry

Fixed size: 12 bytes.

| Field | Type  | Description |
|-------|-------|-------------|
| items | `u32` | number of items |
| size  | `u64` | size in bytes   |

The data entries are stored in the order the tracer reports them (the `data` array of an invocation in the tracer's JSON output). Their count may differ between invocations, even for the same id; an entry that was not recorded is stored as `items = 0, size = 0`.

Records must be ordered so that a parent precedes all of its children (e.g. a pre-order traversal of the invocation tree). Children of the same parent and group are siblings; their order within the run is their order within the group.

A run without `HAS_TS` has no timing information; its records still carry the invocation tree, ids, nodes and data.
A run without `HAS_MEM` has no memory information.

## Mapping from the tracer's JSON output

One JSON invocation tree (see `example.json`) becomes one run block:

| JSON field  | Stored as |
|-------------|-----------|
| `id`        | `id`, an index into the run's id string table |
| `nodeId`    | `node` |
| `ts`        | `ts`, the array in header order; its length must equal `n_ts` |
| `data`      | `n_data` and the data entries, in array order |
| `maxMem`    | `max_mem` (bytes) |
| `children`  | a list of child groups; each child gets `parent` = the index of this record and `group` = the index of its group in this list |

`ts` and `data` are each optional, but at least one must be present. `HAS_TS` is set if the invocations have `ts`, `HAS_DATA` if they have `data`; within one JSON tree, either all invocations have a field or none do. An empty `data` array (`[]`) counts as present and is stored as `n_data = 0`.

`maxMem` is optional. `HAS_MEM` is set if any invocation of the tree has it; invocations without it are stored with `max_mem = 0`.

The timestamp names are not part of the JSON output; the writer supplies them in the header.

## Example layout

```
50 4C 4D 54                 "PLMT"
02                          version 2
18                          24 timestamps
12 00 "DeserializationEnd"  ts_names[0]
...
01 02 00 "q1"               query "q1"
02                          run
03                          flags: HAS_TS | HAS_DATA
04 00                       4 ids
0B 00 "Composition"
04 00 "HTTP"
0E 00 "plume_pq_stage"
0B 00 "plume_stage"
47 00 00 00                 71 records
FF FF FF FF 00 00 00 00      record 0: root, group 0, id "Composition"
00 00 00 00                   node 0
4F 00 00 00 00 00 00 00 ... 0E 92 08 00 00 00 00 00   24 timestamps (79, ..., 561678)
05 00                         5 data entries
00 00 00 00 00 00 00 00 00 00 00 00   items 0, size 0
...
00 00 00 00 00 00 01 00      record 1: parent 0, group 0, id "HTTP"
...                           node, 24 timestamps
01 00                         1 data entry
00 00 00 00 00 00 00 00 00 00 00 00   items 0, size 0
...
```
