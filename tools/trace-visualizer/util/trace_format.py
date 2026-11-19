"""Encoder/decoder for the binary trace format (see FORMAT.md)."""

import gzip
import lzma
import struct

from .model import DataEntry, Invocation, Run, Trace

MAGIC = b"PLMT"
VERSION = 2

TAG_QUERY = 0x01
TAG_RUN = 0x02

FLAG_HAS_TS = 0x01
FLAG_HAS_DATA = 0x02
FLAG_HAS_MEM = 0x04

NO_PARENT = 0xFFFFFFFF

# parent, group, id, node (followed by the optional timestamps and data entries)
_RECORD_HEAD = struct.Struct("<IHHI")
_DATA_ENTRY = struct.Struct("<IQ")  # items, size


class TraceFormatError(Exception):
    pass


# ── Decoding ─────────────────────────────────────────────────────────────────

class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise TraceFormatError(f"unexpected end of file at offset {self.pos}")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def unpack(self, fmt: str | struct.Struct) -> tuple:
        s = fmt if isinstance(fmt, struct.Struct) else struct.Struct(fmt)
        return s.unpack(self.take(s.size))

    def u8(self) -> int:
        return self.unpack("<B")[0]

    def u16(self) -> int:
        return self.unpack("<H")[0]

    def u32(self) -> int:
        return self.unpack("<I")[0]

    def string(self) -> str:
        return self.take(self.u16()).decode("utf-8")


def loads(data: bytes) -> Trace:
    r = _Reader(data)
    if r.take(4) != MAGIC:
        raise TraceFormatError("not a trace file (bad magic)")
    version = r.u8()
    if version != VERSION:
        raise TraceFormatError(f"unsupported format version {version}")

    trace = Trace(ts_names=[r.string() for _ in range(r.u8())])
    ts_struct = struct.Struct(f"<{len(trace.ts_names)}Q")

    current_runs = None
    while not r.eof():
        tag = r.u8()
        if tag == TAG_QUERY:
            current_runs = trace.queries.setdefault(r.string(), [])
        elif tag == TAG_RUN:
            if current_runs is None:
                raise TraceFormatError(f"run block before any query block at offset {r.pos - 1}")
            flags = r.u8()
            if flags & ~(FLAG_HAS_TS | FLAG_HAS_DATA | FLAG_HAS_MEM) or not flags & (FLAG_HAS_TS | FLAG_HAS_DATA):
                raise TraceFormatError(f"invalid run flags 0x{flags:02X} at offset {r.pos - 1}")
            has_ts, has_data = bool(flags & FLAG_HAS_TS), bool(flags & FLAG_HAS_DATA)
            has_mem = bool(flags & FLAG_HAS_MEM)
            if has_ts and not trace.ts_names:
                raise TraceFormatError(f"run with timestamps in a file without timestamp names at offset {r.pos - 1}")
            ids = [r.string() for _ in range(r.u16())]
            run = Run()
            for idx in range(r.u32()):
                parent, group, id_ref, node = r.unpack(_RECORD_HEAD)
                max_mem = r.unpack("<Q")[0] if has_mem else None
                ts = list(r.unpack(ts_struct)) if has_ts else None
                data = [DataEntry(*r.unpack(_DATA_ENTRY)) for _ in range(r.u16())] if has_data else None
                if parent == NO_PARENT:
                    parent = None
                elif parent >= idx:
                    raise TraceFormatError(f"record {idx} references parent {parent} that does not precede it")
                if id_ref >= len(ids):
                    raise TraceFormatError(f"record {idx} references unknown id {id_ref}")
                run.invocations.append(Invocation(ids[id_ref], parent, group, node, ts, data, max_mem))
            current_runs.append(run)
        else:
            raise TraceFormatError(f"unknown block tag 0x{tag:02X} at offset {r.pos - 1}")

    return trace


# File name suffix -> (open function, magic bytes of the compressed stream)
COMPRESSIONS = {
    ".gz": (gzip.open, b"\x1f\x8b"),
    ".xz": (lzma.open, b"\xfd7zXZ\x00"),
}


def _open(path: str, mode: str):
    """Opens `path`, (de)compressing it if its name ends in a COMPRESSIONS suffix."""
    for suffix, (opener, _) in COMPRESSIONS.items():
        if str(path).endswith(suffix):
            return opener(path, mode)
    return open(path, mode)


def read(path: str) -> Trace:
    try:
        with _open(path, "rb") as f:
            data = f.read()
    except (OSError, EOFError, lzma.LZMAError) as e:
        if isinstance(e, FileNotFoundError):
            raise
        raise TraceFormatError(f"cannot decompress: {e}") from None
    if not data.startswith(MAGIC):
        for suffix, (_, magic) in COMPRESSIONS.items():
            if data.startswith(magic):
                raise TraceFormatError(f"file looks compressed; name it with a '{suffix}' suffix to read it")
    return loads(data)


# ── Encoding ─────────────────────────────────────────────────────────────────

def _string(s: str) -> bytes:
    b = s.encode("utf-8")
    if len(b) > 0xFFFF:
        raise TraceFormatError(f"string too long ({len(b)} bytes)")
    return struct.pack("<H", len(b)) + b


def dumps(trace: Trace) -> bytes:
    n_ts = len(trace.ts_names)
    if n_ts > 0xFF:
        raise TraceFormatError(f"too many timestamps ({n_ts}, max 255)")
    ts_struct = struct.Struct(f"<{n_ts}Q")

    out = [MAGIC, struct.pack("<BB", VERSION, n_ts)]
    out += [_string(name) for name in trace.ts_names]

    for qname, runs in trace.queries.items():
        out += [struct.pack("<B", TAG_QUERY), _string(qname)]
        for run in runs:
            ids: dict[str, int] = {}
            for inv in run.invocations:
                ids.setdefault(inv.id, len(ids))
            if len(ids) > 0xFFFF:
                raise TraceFormatError(f"too many distinct ids in one run ({len(ids)})")

            has_mem = run.has_mem
            if run.invocations:
                has_ts, has_data = run.has_ts, run.has_data
                if not (has_ts or has_data):
                    raise TraceFormatError(f"run in query '{qname}' has neither timestamps nor data")
            else:
                has_ts, has_data = n_ts > 0, n_ts == 0  # empty run: any valid flags will do
            if has_ts and n_ts == 0:
                raise TraceFormatError(f"run in query '{qname}' has timestamps, but the trace has no timestamp names")
            flags = (FLAG_HAS_TS if has_ts else 0) | (FLAG_HAS_DATA if has_data else 0) | (FLAG_HAS_MEM if has_mem else 0)

            out += [struct.pack("<BBH", TAG_RUN, flags, len(ids))]
            out += [_string(s) for s in ids]
            out += [struct.pack("<I", len(run.invocations))]
            for idx, inv in enumerate(run.invocations):
                if (inv.ts is not None) != has_ts or (inv.data is not None) != has_data \
                        or (inv.max_mem is not None) != has_mem:
                    raise TraceFormatError(f"invocation {idx} in query '{qname}': all invocations of a run "
                                           "must either have timestamps (data, memory) or not")
                if inv.parent is not None and inv.parent >= idx:
                    raise TraceFormatError(f"invocation {idx} references parent {inv.parent} that does not precede it")
                parent = NO_PARENT if inv.parent is None else inv.parent
                out.append(_RECORD_HEAD.pack(parent, inv.group, ids[inv.id], inv.node))
                if has_mem:
                    out.append(struct.pack("<Q", inv.max_mem))
                if has_ts:
                    if len(inv.ts) != n_ts:
                        raise TraceFormatError(f"invocation {idx} has {len(inv.ts)} timestamps, expected {n_ts}")
                    out.append(ts_struct.pack(*inv.ts))
                if has_data:
                    if len(inv.data) > 0xFFFF:
                        raise TraceFormatError(f"invocation {idx} has too many data entries ({len(inv.data)})")
                    out.append(struct.pack("<H", len(inv.data)))
                    out += [_DATA_ENTRY.pack(d.items, d.size) for d in inv.data]

    return b"".join(out)


def write(trace: Trace, path: str) -> None:
    data = dumps(trace)
    with _open(path, "wb") as f:
        f.write(data)
