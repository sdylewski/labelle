"""Rich text layout for labels: font fallback for symbols, plus a small math markup.

Math markup (only when math mode is on):

    x^2   x^10   x^{n+1}     superscript (a digit run, one character, or a {group})
    H_2O  a_{ij}             subscript
    \\sqrt{x}                 square root with an overbar; \\sqrt[3]{x} for nth roots
    \\frac{a}{b}              stacked fraction
    \\pi \\pm \\le \\infty ...   named symbols (see SYMBOLS)
    \\^  \\_  \\{  \\}  \\\\        literal characters

Characters missing from the selected font are drawn with a fallback font
(DejaVu Sans, Noto Sans Math, ...) in both plain and math mode.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageDraw, ImageFont

LOG = logging.getLogger(__name__)

SYMBOLS: dict[str, str] = {
    # Greek lowercase
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    # Greek uppercase
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    # Operators and relations
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "·", "ast": "∗",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "ll": "≪", "gg": "≫",
    # Big operators / calculus
    "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "oint": "∮",
    "partial": "∂", "nabla": "∇", "infty": "∞", "lim": "lim",
    # Arrows
    "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "uparrow": "↑", "downarrow": "↓",
    # Sets and logic
    "in": "∈", "notin": "∉", "subset": "⊂", "supset": "⊃", "subseteq": "⊆",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "land": "∧", "lor": "∨", "therefore": "∴", "because": "∵",
    "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "R": "ℝ", "C": "ℂ",
    # Misc
    "deg": "°", "degree": "°", "circ": "∘", "angle": "∠", "perp": "⊥",
    "parallel": "∥", "permil": "‰", "ohm": "Ω", "micro": "µ", "hbar": "ℏ",
    "ell": "ℓ", "prime": "′", "dprime": "″", "cdots": "⋯", "ldots": "…",
    "sqrt": "√",  # only used when \sqrt has no argument
}

_SUP_SCALE = 0.62
_STRUCT_SCALE = 0.72  # fraction parts and root index
_MISSING_CODEPOINT = "\U0010fffd"


# --------------------------------------------------------------------- fonts

_FALLBACK_CANDIDATES = (
    ("DejaVu Sans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("Noto Sans Math", "/usr/share/fonts/truetype/noto/NotoSansMath-Regular.ttf"),
    ("DejaVu Math TeX Gyre", "/usr/share/fonts/truetype/dejavu/DejaVuMathTeXGyre.ttf"),
    ("Noto Sans Symbols2", "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf"),
    ("Noto Sans Symbols", "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf"),
)


def _fc_match(family: str, bold: bool) -> Path | None:
    if shutil.which("fc-match") is None:
        return None
    pattern = f"{family}:bold" if bold else family
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{family}\n%{file}", pattern],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return None
    if len(out) >= 2 and family.lower() in out[0].lower():
        return Path(out[1])
    return None


@functools.lru_cache(maxsize=4)
def fallback_font_paths(bold: bool = False) -> tuple[Path, ...]:
    paths: list[Path] = []
    for family, default_path in _FALLBACK_CANDIDATES:
        candidate = None
        if bold and family == "DejaVu Sans":
            p = Path(default_path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"))
            candidate = p if p.exists() else None
        if candidate is None:
            p = Path(default_path)
            candidate = p if p.exists() else _fc_match(family, bold)
        if candidate is not None and candidate not in paths:
            paths.append(candidate)
    if not paths:
        LOG.debug("No fallback fonts found; missing symbols will show as boxes")
    return tuple(paths)


@functools.lru_cache(maxsize=256)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(1, size))


@functools.lru_cache(maxsize=64)
def _missing_mask(path: str) -> tuple:
    font = _font(path, 48)
    mask = font.getmask(_MISSING_CODEPOINT)
    return (mask.size, bytes(mask))


@functools.lru_cache(maxsize=8192)
def has_glyph(path: str, char: str) -> bool:
    if char.isspace():
        return True
    font = _font(path, 48)
    mask = font.getmask(char)
    return (mask.size, bytes(mask)) != _missing_mask(path)


class FontSet:
    """A primary font plus fallbacks, all at one pixel size."""

    def __init__(self, primary: str, size: int):
        self.primary = primary
        self.size = max(1, int(round(size)))
        bold = "bold" in Path(primary).stem.lower()
        self.fallbacks = [str(p) for p in fallback_font_paths(bold)]

    def path_for(self, char: str) -> str:
        if has_glyph(self.primary, char):
            return self.primary
        for path in self.fallbacks:
            if has_glyph(path, char):
                return path
        return self.primary

    def font(self, path: str | None = None) -> ImageFont.FreeTypeFont:
        return _font(path or self.primary, self.size)

    def scaled(self, factor: float) -> FontSet:
        return FontSet(self.primary, round(self.size * factor))


def text_needs_fallback(text: str, font_path: str) -> bool:
    return any(not has_glyph(font_path, ch) for ch in text)


# -------------------------------------------------------------------- parser


@dataclass
class Node:
    kind: str  # "text", "sup", "sub", "sqrt", "frac"
    text: str = ""
    children: list[Node] = field(default_factory=list)
    extra: list[Node] = field(default_factory=list)  # frac denominator / root index


class _Parser:
    def __init__(self, src: str):
        self.s = src
        self.i = 0

    def parse(self) -> list[Node]:
        nodes = self._sequence(stop_at_brace=False)
        return nodes

    def _peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def _sequence(self, stop_at_brace: bool) -> list[Node]:
        nodes: list[Node] = []
        buf: list[str] = []

        def flush():
            if buf:
                nodes.append(Node("text", "".join(buf)))
                buf.clear()

        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "}" and stop_at_brace:
                break
            if c == "\\":
                node = self._command()
                if node.kind == "text":
                    buf.append(node.text)
                else:
                    flush()
                    nodes.append(node)
            elif c in "^_":
                self.i += 1
                arg = self._script_argument()
                if arg is None:
                    buf.append(c)
                else:
                    flush()
                    nodes.append(Node("sup" if c == "^" else "sub", children=arg))
            elif c == "{":
                self.i += 1
                inner = self._sequence(stop_at_brace=True)
                if self._peek() == "}":
                    self.i += 1
                flush()
                nodes.extend(inner)
            else:
                buf.append(c)
                self.i += 1
        flush()
        return nodes

    def _group(self) -> list[Node] | None:
        """Parse a {group}, or a single character / command."""
        c = self._peek()
        if not c or c.isspace():
            return None
        if c == "{":
            self.i += 1
            inner = self._sequence(stop_at_brace=True)
            if self._peek() == "}":
                self.i += 1
            return inner
        if c == "\\":
            return [self._command()]
        self.i += 1
        return [Node("text", c)]

    def _script_argument(self) -> list[Node] | None:
        c = self._peek()
        if c.isdigit():
            start = self.i
            while self._peek().isdigit():
                self.i += 1
            return [Node("text", self.s[start : self.i])]
        if c == "-" and self.i + 1 < len(self.s) and self.s[self.i + 1].isdigit():
            start = self.i
            self.i += 1
            while self._peek().isdigit():
                self.i += 1
            return [Node("text", "−" + self.s[start + 1 : self.i])]
        return self._group()

    def _command(self) -> Node:
        assert self.s[self.i] == "\\"
        self.i += 1
        start = self.i
        while self._peek().isalpha():
            self.i += 1
        name = self.s[start : self.i]
        if not name:
            # Escaped literal like \^ \_ \{ \} \\ or a lone trailing backslash
            ch = self._peek()
            if ch:
                self.i += 1
                return Node("text", ch)
            return Node("text", "\\")
        if name == "sqrt":
            index = None
            if self._peek() == "[":
                end = self.s.find("]", self.i)
                if end != -1:
                    index = _Parser(self.s[self.i + 1 : end]).parse()
                    self.i = end + 1
            arg = self._group()
            if arg is None:
                return Node("text", "√")
            return Node("sqrt", children=arg, extra=index or [])
        if name == "frac":
            num = self._group()
            den = self._group() if num is not None else None
            if num is None or den is None:
                return Node("text", "\\frac")
            return Node("frac", children=num, extra=den)
        if name in SYMBOLS:
            return Node("text", SYMBOLS[name])
        return Node("text", "\\" + name)


def parse_math(src: str) -> list[Node]:
    return _Parser(src).parse()


# -------------------------------------------------------------------- layout


@dataclass
class Box:
    width: float
    ascent: float  # above baseline (positive)
    descent: float  # below baseline (positive)
    ops: list[tuple] = field(default_factory=list)  # relative to (0, baseline)

    @property
    def height(self) -> float:
        return self.ascent + self.descent


def _shift(ops: list[tuple], dx: float, dy: float) -> list[tuple]:
    out = []
    for op in ops:
        if op[0] == "text":
            _, x, y, text, path, size = op
            out.append(("text", x + dx, y + dy, text, path, size))
        else:
            _, pts, width = op
            out.append(("line", [(x + dx, y + dy) for x, y in pts], width))
    return out


def _layout_text(text: str, fonts: FontSet) -> Box:
    ops = []
    x = 0.0
    run: list[str] = []
    run_path: str | None = None
    ascent, descent = fonts.font().getmetrics()

    def flush():
        nonlocal x
        if run:
            s = "".join(run)
            font = fonts.font(run_path)
            ops.append(("text", x, 0.0, s, run_path, fonts.size))
            x += font.getlength(s)
            run.clear()

    for ch in text:
        path = fonts.path_for(ch)
        if path != run_path:
            flush()
            run_path = path
            a, d = fonts.font(path).getmetrics()
            ascent, descent = max(ascent, a), max(descent, d)
        run.append(ch)
    flush()
    # Use the primary font's metrics so mixed lines stay steady; fallback fonts
    # often have very tall line metrics.
    a, d = fonts.font().getmetrics()
    return Box(x, a, d, ops)


def _hcat(boxes: list[Box]) -> Box:
    x = 0.0
    ops: list[tuple] = []
    ascent = descent = 0.0
    for b in boxes:
        ops += _shift(b.ops, x, 0)
        x += b.width
        ascent = max(ascent, b.ascent)
        descent = max(descent, b.descent)
    return Box(x, ascent, descent, ops)


def layout_nodes(nodes: list[Node], fonts: FontSet) -> Box:
    boxes: list[Box] = []
    size = fonts.size
    stroke = max(1, round(size * 0.06))
    i = 0
    while i < len(nodes):
        node = nodes[i]
        i += 1
        if node.kind == "text":
            boxes.append(_layout_text(node.text, fonts))
        elif node.kind in ("sup", "sub"):
            scripts = [node]
            # x_a^b / x^b_a: stack both scripts at the same position
            if i < len(nodes) and {node.kind, nodes[i].kind} == {"sup", "sub"}:
                scripts.append(nodes[i])
                i += 1
            width = ascent = descent = 0.0
            ops: list[tuple] = []
            for script in scripts:
                inner = layout_nodes(script.children, fonts.scaled(_SUP_SCALE))
                dy = -size * 0.42 if script.kind == "sup" else size * 0.18
                width = max(width, inner.width)
                ascent = max(ascent, inner.ascent - dy)
                descent = max(descent, inner.descent + dy)
                ops += _shift(inner.ops, 0, dy)
            boxes.append(
                Box(width + size * 0.03, max(0.0, ascent), max(0.0, descent), ops)
            )
        elif node.kind == "sqrt":
            inner = layout_nodes(node.children, fonts)
            pad = max(1.0, size * 0.08)
            top = -(inner.ascent + pad)
            bottom = inner.descent
            h = bottom - top
            r = max(size * 0.45, 4.0)
            lead = 0.0
            ops: list[tuple] = []
            if node.extra:  # nth-root index sits in the radical's crook
                idx = layout_nodes(node.extra, fonts.scaled(_SUP_SCALE * 0.85))
                lead = max(0.0, idx.width - r * 0.35)
                ops += _shift(idx.ops, 0, top + h * 0.45 - idx.descent)
            pts = [
                (lead, top + h * 0.62),
                (lead + r * 0.22, top + h * 0.52),
                (lead + r * 0.5, bottom),
                (lead + r, top),
                (lead + r + inner.width + pad, top),
            ]
            ops.append(("line", pts, stroke))
            ops += _shift(inner.ops, lead + r + pad * 0.5, 0)
            boxes.append(
                Box(lead + r + inner.width + pad * 1.5, -top + stroke, bottom, ops)
            )
        elif node.kind == "frac":
            part_fonts = fonts.scaled(_STRUCT_SCALE)
            num = layout_nodes(node.children, part_fonts)
            den = layout_nodes(node.extra, part_fonts)
            axis = -size * 0.28  # fraction bar height (math axis)
            gap = max(1.0, size * 0.06)
            width = max(num.width, den.width) + size * 0.2
            ops = []
            ops += _shift(num.ops, (width - num.width) / 2, axis - gap - num.descent)
            ops += _shift(den.ops, (width - den.width) / 2, axis + gap + den.ascent)
            ops.append(("line", [(size * 0.05, axis), (width - size * 0.05, axis)], stroke))
            boxes.append(
                Box(
                    width,
                    -axis + gap + num.height,
                    max(0.0, axis + gap + den.height),
                    ops,
                )
            )
    if not boxes:
        a, d = fonts.font().getmetrics()
        return Box(0.0, a, d, [])
    return _hcat(boxes)


def layout_line(line: str, font_path: str, size: int, math: bool) -> Box:
    fonts = FontSet(font_path, size)
    nodes = parse_math(line) if math else [Node("text", line)]
    return layout_nodes(nodes, fonts)


def draw_box(draw: ImageDraw.ImageDraw, box: Box, x: float, baseline: float) -> None:
    for op in box.ops:
        if op[0] == "text":
            _, ox, oy, text, path, size = op
            draw.text(
                (round(x + ox), round(baseline + oy)),
                text,
                font=_font(path, size),
                anchor="ls",
                fill=1,
            )
        else:
            _, pts, width = op
            draw.line(
                [(round(x + px), round(baseline + py)) for px, py in pts],
                fill=1,
                width=width,
                joint="curve",
            )
