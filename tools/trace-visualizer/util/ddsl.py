"""Minimal parser for Dandelion composition files (`.ddsl`).

Supported grammar (whitespace-insensitive, `//`, `#` and `/* */` comments are ignored):

    function NAME (PARAM, ...) => (OUT, ...);
    composition NAME (IN, ...) => (OUT, ...) {
        FUNC (PARAM = DIST SET, PARAM = DIST {SET, SET}, ...) => (SET = OUT, ...) [by ...];
        ...
    }

The distribution keyword (`all`, `each`, `keyed`, ...) is optional. Everything between `by`
and the terminating `;` is kept verbatim as the statement's join clause.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


class DdslError(Exception):
    pass


@dataclass
class Function:
    name: str
    params: list[str]   # input set names, in order (= order of the trace's data entries)
    outputs: list[str]  # output set names, in order


@dataclass
class Arg:
    param: str          # input set of the function
    dist: str | None    # distribution keyword (all, each, keyed, ...)
    sources: list[str]  # composition-level sets feeding this input set


@dataclass
class Statement:
    func: str
    args: list[Arg]
    outputs: dict[str, str]  # function output set -> composition-level set it is bound to
    by: str | None           # join clause, e.g. "regionInfo inner inBuffers"


@dataclass
class Composition:
    name: str
    inputs: list[str]
    outputs: list[str]
    statements: list[Statement] = field(default_factory=list)


@dataclass
class Program:
    functions: dict[str, Function] = field(default_factory=dict)
    compositions: dict[str, Composition] = field(default_factory=dict)


_TOKEN = re.compile(r"\s*(=>|[(){},;=]|[A-Za-z_][A-Za-z0-9_.\-]*|\S)")
_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*|#[^\n]*", re.S)


class _Parser:
    def __init__(self, text: str, source: str):
        text = _COMMENTS.sub(" ", text)
        self.tokens = [m.group(1) for m in _TOKEN.finditer(text) if m.group(1)]
        self.pos = 0
        self.source = source

    def error(self, msg: str) -> DdslError:
        near = " ".join(self.tokens[max(0, self.pos - 3):self.pos + 3])
        return DdslError(f"{self.source}: {msg} (near '{near}')")

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self) -> str:
        tok = self.peek()
        if tok is None:
            raise self.error("unexpected end of file")
        self.pos += 1
        return tok

    def expect(self, tok: str) -> None:
        got = self.next()
        if got != tok:
            self.pos -= 1
            raise self.error(f"expected '{tok}', got '{got}'")

    def ident(self) -> str:
        tok = self.next()
        if not re.match(r"[A-Za-z_]", tok):
            self.pos -= 1
            raise self.error(f"expected identifier, got '{tok}'")
        return tok

    def ident_list(self) -> list[str]:
        self.expect("(")
        names = []
        while self.peek() != ")":
            names.append(self.ident())
            if self.peek() == ",":
                self.next()
        self.expect(")")
        return names

    def program(self, prog: Program) -> None:
        while self.peek() is not None:
            kw = self.next()
            if kw == "function":
                name = self.ident()
                params = self.ident_list()
                self.expect("=>")
                outputs = self.ident_list()
                self.expect(";")
                prog.functions[name] = Function(name, params, outputs)
            elif kw == "composition":
                comp = self.composition()
                prog.compositions[comp.name] = comp
            else:
                self.pos -= 1
                raise self.error(f"expected 'function' or 'composition', got '{kw}'")

    def composition(self) -> Composition:
        comp = Composition(self.ident(), [], [])
        comp.inputs = self.ident_list()
        self.expect("=>")
        comp.outputs = self.ident_list()
        self.expect("{")
        while self.peek() != "}":
            comp.statements.append(self.statement())
        self.expect("}")
        if self.peek() == ";":
            self.next()
        return comp

    def statement(self) -> Statement:
        func = self.ident()
        self.expect("(")
        args = []
        while self.peek() != ")":
            param = self.ident()
            self.expect("=")
            dist = None
            if self.peek() not in ("{", ",", ")") and self.pos + 1 < len(self.tokens) \
                    and self.tokens[self.pos + 1] not in (",", ")"):
                dist = self.ident()
            if self.peek() == "{":
                self.next()
                sources = []
                while self.peek() != "}":
                    sources.append(self.ident())
                    if self.peek() == ",":
                        self.next()
                self.expect("}")
            else:
                sources = [self.ident()]
            args.append(Arg(param, dist, sources))
            if self.peek() == ",":
                self.next()
        self.expect(")")
        self.expect("=>")
        self.expect("(")
        outputs = {}
        while self.peek() != ")":
            target = self.ident()
            self.expect("=")
            outputs[self.ident()] = target
            if self.peek() == ",":
                self.next()
        self.expect(")")
        by = None
        if self.peek() == "by":
            self.next()
            words = []
            while self.peek() not in (";", None):
                words.append(self.next())
            by = " ".join(words)
        self.expect(";")
        return Statement(func, args, outputs, by)


def parse(text: str, prog: Program | None = None, source: str = "<ddsl>") -> Program:
    prog = prog or Program()
    _Parser(text, source).program(prog)
    return prog


def read(paths: list[str]) -> Program:
    """Parses all given files (directories are searched for `*.ddsl`) into one program."""
    prog = Program()
    for p in paths:
        path = Path(p)
        files = sorted(path.glob("*.ddsl")) if path.is_dir() else [path]
        for f in files:
            parse(f.read_text(), prog, str(f))
    return prog
