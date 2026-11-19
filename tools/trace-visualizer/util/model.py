"""In-memory representation of a decoded trace."""

from dataclasses import dataclass, field


@dataclass
class DataEntry:
    items: int
    size: int  # in bytes


@dataclass
class Invocation:
    id: str
    parent: int | None  # index of the parent invocation within the run, None for roots
    group: int          # index of the parent's child group this invocation belongs to
    node: int
    # One value per Trace.ts_names entry, in microseconds; 0 = not recorded. None if the run has no timestamps.
    ts: list[int] | None
    # In the order reported by the tracer. None if the run has no data.
    data: list[DataEntry] | None
    # Maximum memory used by the invocation in bytes; 0 = not recorded. None if the run has no memory information.
    max_mem: int | None = None


@dataclass
class Run:
    # Within a run, either all invocations have `ts` (`data`) or none do.
    invocations: list[Invocation] = field(default_factory=list)

    @property
    def has_ts(self) -> bool:
        return bool(self.invocations) and self.invocations[0].ts is not None

    @property
    def has_data(self) -> bool:
        return bool(self.invocations) and self.invocations[0].data is not None

    @property
    def has_mem(self) -> bool:
        return bool(self.invocations) and self.invocations[0].max_mem is not None


@dataclass
class Trace:
    ts_names: list[str]
    queries: dict[str, list[Run]] = field(default_factory=dict)
