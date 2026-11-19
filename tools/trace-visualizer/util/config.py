"""Loading and validation of the visualization config (see README.md)."""

import colorsys
import json
from dataclasses import dataclass

# A reference is either a timestamp name or a numeric literal (in trace time units).
Ref = str | int | float


@dataclass
class Bar:
    label: str
    start: list[Ref]
    end: list[Ref]
    face: str  # fill color
    edge: str  # outline color


@dataclass
class Config:
    bars: list[Bar]
    span_start: list[Ref]
    span_end: list[Ref]
    remote: str | None  # timestamp marking an invocation as executed remotely when set

    def referenced_names(self) -> set[str]:
        refs = [*self.span_start, *self.span_end]
        for bar in self.bars:
            refs += [*bar.start, *bar.end]
        names = {r for r in refs if isinstance(r, str)}
        if self.remote:
            names.add(self.remote)
        return names


class ConfigError(Exception):
    pass


def _refs(value, where: str) -> list[Ref]:
    refs = value if isinstance(value, list) else [value]
    if not refs:
        raise ConfigError(f"{where}: must not be empty")
    for r in refs:
        if isinstance(r, bool) or not isinstance(r, (str, int, float)):
            raise ConfigError(f"{where}: expected timestamp name or number, got {r!r}")
    return refs


def _hex_to_hls(color: str) -> tuple[float, float, float]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ConfigError(f"invalid color {color!r}, expected #RGB or #RRGGBB")
    try:
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        raise ConfigError(f"invalid color {color!r}, expected #RGB or #RRGGBB") from None
    return colorsys.rgb_to_hls(r, g, b)


def _hls_to_hex(h: float, l: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"


def _edge_of(face: str) -> str:
    h, _, s = _hex_to_hls(face)
    return _hls_to_hex(h, 0.35, s)


def load(path: str) -> Config:
    with open(path) as f:
        raw = json.load(f)

    raw_bars = raw.get("bars")
    if not isinstance(raw_bars, list) or not raw_bars:
        raise ConfigError("'bars' must be a non-empty list")

    # Bars without an explicit color get evenly spaced hues
    uncolored = [i for i, b in enumerate(raw_bars) if "color" not in b]
    auto_hue = {i: n / len(uncolored) for n, i in enumerate(uncolored)}

    bars = []
    for i, b in enumerate(raw_bars):
        where = f"bars[{i}]"
        for key in ("label", "start", "end"):
            if key not in b:
                raise ConfigError(f"{where}: missing '{key}'")
        if "color" in b:
            face = b["color"]
            _hex_to_hls(face)  # validate
        else:
            face = _hls_to_hex(auto_hue[i], 0.85, 0.85)
        bars.append(Bar(
            label=str(b["label"]),
            start=_refs(b["start"], f"{where}.start"),
            end=_refs(b["end"], f"{where}.end"),
            face=face,
            edge=_edge_of(face),
        ))

    span = raw.get("span", {})
    remote = raw.get("remote")
    if remote is not None and not isinstance(remote, str):
        raise ConfigError("'remote' must be a timestamp name")

    return Config(
        bars=bars,
        span_start=_refs(span["start"], "span.start") if "start" in span else [],
        span_end=_refs(span["end"], "span.end") if "end" in span else [],
        remote=remote,
    )
