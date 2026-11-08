"""Equation editor dialog: LaTeX-like source, symbol palette, live preview."""

from __future__ import annotations

import logging
import re

from PIL import Image, ImageOps, ImageQt
from PyQt6 import QtCore
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPixmap,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from labelle.lib.constants import PIXELS_PER_MM, Direction
from labelle.lib.render_engines import RenderContext, TextRenderEngine
from labelle.lib.render_engines.math_text import KNOWN_COMMANDS, SYMBOLS, check_math

LOG = logging.getLogger(__name__)

# (button text, text to insert, cursor steps back from the end, tooltip)
STRUCTURES: list[tuple[str, str, int, str]] = [
    ("x²", "^{2}", 0, "Squared   ^2"),
    ("xⁿ", "^{}", 1, "Power   ^{…}"),
    ("xₙ", "_{}", 1, "Subscript   _{…}"),
    ("xₙᵐ", "_{}^{}", 4, "Sub- and superscript   _{…}^{…}"),
    ("√x", r"\sqrt{}", 1, r"Square root   \sqrt{…}"),
    ("ⁿ√x", r"\sqrt[n]{}", 1, r"Nth root   \sqrt[n]{…}"),
    ("a⁄b", r"\frac{}{}", 3, r"Fraction   \frac{top}{bottom}"),
    ("( )", r"\left( \right)", 7, r"Parentheses   \left( … \right)"),
    ("|x|", r"\left| \right|", 7, r"Absolute value   \left| … \right|"),
    ("x̄", r"\bar{}", 1, r"Bar (mean, conjugate)   \bar{…}"),
    ("A̅B̅", r"\overline{}", 1, r"Overline across everything   \overline{…}"),
    ("x⃗", r"\vec{}", 1, r"Vector arrow   \vec{…}"),
    ("x̂", r"\hat{}", 1, r"Hat   \hat{…}"),
    ("ẋ", r"\dot{}", 1, r"Dot   \dot{…}"),
    ("x̃", r"\tilde{}", 1, r"Tilde   \tilde{…}"),
    ("∑", r"\sum_{i=1}^{n} ", 0, r"Sum   \sum_{i=1}^{n}"),
    ("∫", r"\int_{a}^{b} ", 0, r"Integral   \int_{a}^{b}"),
    ("lim", r"\lim_{x \to 0} ", 0, r"Limit   \lim_{x \to 0}"),
    ("sin", r"\sin ", 0, r"\sin  (also \cos \tan \log \ln \exp …)"),
    ("log", r"\log_{} ", 2, r"Logarithm   \log_{base}"),
    ("Abc", r"\text{}", 1, r"Plain text   \text{…}"),
    ("𝐁", r"\mathbf{}", 1, r"Bold   \mathbf{…}"),
    ("␣", r"\quad ", 0, r"Wide space   \quad   (thin: \,)"),
]

SYMBOL_GROUPS: list[tuple[str, str]] = [
    ("Greek", "α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω"),
    ("Operators", "+ − ± ∓ × ÷ · ∗ √ ∛ ∑ ∏ ∫ ∬ ∮ ∂ ∇ ∞ ∘"),
    ("Relations", "= ≠ ≈ ≡ ∼ ∝ < > ≤ ≥ ≪ ≫"),
    ("Arrows", "→ ← ↔ ⇒ ⇐ ⇔ ↑ ↓"),
    ("Sets & logic", "∈ ∉ ⊂ ⊃ ⊆ ∪ ∩ ∅ ∀ ∃ ¬ ∧ ∨ ∴ ∵ ℕ ℤ ℚ ℝ ℂ"),
    ("Units & misc", "° ℃ ℉ Ω µ Å ℓ ′ ″ ∠ ⊥ ∥ … ⋯ ℏ ‰ ½ ¼ ¾"),
]

HELP_HTML = r"""
<h3>Equation syntax</h3>
<table cellspacing="4">
<tr><td><code>x^2</code> &nbsp; <code>x^{n+1}</code></td><td>powers</td></tr>
<tr><td><code>H_2O</code> &nbsp; <code>a_{ij}</code></td><td>subscripts</td></tr>
<tr><td><code>\sqrt{x}</code> &nbsp; <code>\sqrt[3]{x}</code></td><td>roots</td></tr>
<tr><td><code>\frac{a}{b}</code></td><td>fraction</td></tr>
<tr><td><code>\left( … \right)</code></td><td>brackets</td></tr>
<tr><td><code>\bar{x} \overline{AB} \vec{v} \hat{x} \dot{x}</code></td><td>accents</td></tr>
<tr><td><code>\text{Area}</code> &nbsp; <code>\mathbf{F}</code></td><td>plain text / bold</td></tr>
<tr><td><code>\sin \cos \log \ln \lim</code></td><td>function names</td></tr>
<tr><td><code>\pi \alpha \Delta \pm \times \le \ne \approx \infty</code></td><td>symbols</td></tr>
<tr><td><code>\,</code> &nbsp; <code>\quad</code></td><td>thin / wide space</td></tr>
<tr><td><code>\^ \_ \{ \} \\</code></td><td>literal characters</td></tr>
</table>
<p>Each line of the source is a line on the label. Spaces are kept as typed.<br>
Symbols can also be typed directly (π, ≤, °…) or picked from the palette.</p>
"""

_SYMBOL_TO_COMMAND: dict[str, str] = {}
for _name, _sym in SYMBOLS.items():
    if len(_sym) == 1 and _sym not in _SYMBOL_TO_COMMAND:
        _SYMBOL_TO_COMMAND[_sym] = _name


class LatexHighlighter(QSyntaxHighlighter):
    _command_re = re.compile(r"\\([A-Za-z]+|.)")

    def __init__(self, document) -> None:
        super().__init__(document)
        pal = QApplication.palette()
        accent = pal.color(pal.ColorRole.Highlight)
        self._cmd = QTextCharFormat()
        self._cmd.setForeground(accent)
        self._cmd.setFontWeight(QFont.Weight.DemiBold)
        self._bad = QTextCharFormat()
        self._bad.setForeground(QColor("#d64545"))
        self._bad.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        self._bad.setUnderlineColor(QColor("#d64545"))
        self._brace = QTextCharFormat()
        self._brace.setForeground(QColor("#9a6dd7"))
        self._brace.setFontWeight(QFont.Weight.Bold)
        self._script = QTextCharFormat()
        self._script.setForeground(QColor("#d9822b"))
        self._script.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str | None) -> None:  # noqa: N802
        if not text:
            return
        for i, ch in enumerate(text):
            if ch in "{}[]":
                self.setFormat(i, 1, self._brace)
            elif ch in "^_":
                self.setFormat(i, 1, self._script)
        for m in self._command_re.finditer(text):
            name = m.group(1)
            ok = not name.isalpha() or name in KNOWN_COMMANDS
            self.setFormat(m.start(), m.end() - m.start(), self._cmd if ok else self._bad)


class EquationEditorDialog(QDialog):
    def __init__(
        self,
        source: str,
        font_path: str,
        font_size_ratio: float = 0.9,
        height_px: int = 64,
        align: Direction = Direction.CENTER,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Equation Editor")
        self.resize(960, 660)
        self._font_path = font_path
        self._font_size_ratio = font_size_ratio
        self._height_px = height_px
        self._align = align

        self._editor = QPlainTextEdit()
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(max(mono.pointSize(), 12))
        self._editor.setFont(mono)
        self._editor.setPlaceholderText(r"e.g.  E = mc^2   or   x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}")
        self._editor.setPlainText(source)
        self._editor.setTabChangesFocus(True)
        self._highlighter = LatexHighlighter(self._editor.document())

        self._problems = QLabel()
        self._problems.setWordWrap(True)
        self._preview = QLabel()
        self._preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview_info = QLabel()
        self._preview_info.setObjectName("muted")

        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._update_preview)
        self._editor.textChanged.connect(self._timer.start)

        self._build_layout()
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.accept)
        self._update_preview()
        cursor = self._editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    # ----------------------------------------------------------------- layout

    def _palette_button(self, text: str, tip: str, slot) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setMinimumSize(40, 34)
        b.setStyleSheet("QToolButton { font-size: 13pt; }")
        b.setAutoRaise(False)
        b.clicked.connect(slot)
        return b

    def _grid(self, buttons: list[QToolButton], columns: int) -> QWidget:
        w = QWidget()
        grid = QGridLayout(w)
        grid.setSpacing(4)
        grid.setContentsMargins(6, 6, 6, 6)
        for i, b in enumerate(buttons):
            grid.addWidget(b, i // columns, i % columns)
        grid.setColumnStretch(columns, 1)
        grid.setRowStretch(len(buttons) // columns + 1, 1)
        return w

    def _build_layout(self) -> None:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        structure_buttons = [
            self._palette_button(
                label, tip, lambda _=False, t=text, b=back: self.insert(t, b)
            )
            for label, text, back, tip in STRUCTURES
        ]
        tabs.addTab(self._grid(structure_buttons, 12), "Structures")
        for title, symbols in SYMBOL_GROUPS:
            buttons = []
            for sym in symbols.split():
                cmd = _SYMBOL_TO_COMMAND.get(sym)
                tip = f"{sym}   (or type \\{cmd})" if cmd else sym
                buttons.append(
                    self._palette_button(sym, tip, lambda _=False, t=sym: self.insert(t))
                )
            tabs.addTab(self._grid(buttons, 16), title.replace("&", "&&"))
        tabs.setMaximumHeight(130)

        source_title = QLabel("Source")
        source_title.setObjectName("sectionTitle")
        help_button = QPushButton("Syntax help")
        help_button.setCheckable(True)
        help_text = QLabel(HELP_HTML)
        help_text.setTextFormat(QtCore.Qt.TextFormat.RichText)
        help_text.setWordWrap(True)
        help_text.setVisible(False)
        help_button.toggled.connect(help_text.setVisible)

        header = QHBoxLayout()
        header.addWidget(source_title)
        header.addStretch(1)
        header.addWidget(help_button)

        preview_title = QLabel("Preview")
        preview_title.setObjectName("sectionTitle")
        pheader = QHBoxLayout()
        pheader.addWidget(preview_title)
        pheader.addStretch(1)
        pheader.addWidget(self._preview_info)

        canvas = QScrollArea()
        self._canvas = canvas
        canvas.setObjectName("previewCanvas")
        canvas.setWidgetResizable(True)
        canvas.setMinimumHeight(170)
        inner = QWidget()
        inner.setObjectName("previewCanvasInner")
        il = QVBoxLayout(inner)
        il.addWidget(self._preview, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        canvas.setWidget(inner)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Use Equation")
            ok.setObjectName("printButton")  # primary accent style
            ok.setToolTip("Ctrl+Enter")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.addWidget(tabs)
        cl.addLayout(header)
        cl.addWidget(self._editor, 1)
        cl.addWidget(self._problems)
        cl.addWidget(help_text)

        layout = QVBoxLayout(self)
        layout.addWidget(card, 3)
        layout.addLayout(pheader)
        layout.addWidget(canvas, 2)
        layout.addWidget(buttons)

    # ---------------------------------------------------------------- actions

    def insert(self, text: str, cursor_back: int = 0) -> None:
        cursor = self._editor.textCursor()
        selected = cursor.selectedText()
        if selected and cursor_back and "{}" in text:
            # Wrap the selection: select "x", click √ → \sqrt{x}
            idx = text.index("{}") + 1
            text = text[:idx] + selected + text[idx:]
            cursor_back = 0
        cursor.insertText(text)
        if cursor_back:
            cursor.movePosition(
                cursor.MoveOperation.Left, cursor.MoveMode.MoveAnchor, cursor_back
            )
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def source(self) -> str:
        return self._editor.toPlainText()

    def _update_preview(self) -> None:
        src = self.source()
        problems = check_math(src)
        if problems:
            self._problems.setText("⚠  " + "\n⚠  ".join(problems))
            self._problems.setStyleSheet("color: #d9822b;")
        else:
            self._problems.setText("✓  Looks good")
            self._problems.setStyleSheet("color: #3a9d5d;")
        lines = src.splitlines() or [" "]
        try:
            bitmap = TextRenderEngine(
                text_lines=lines,
                font_file_name=self._font_path,
                font_size_ratio=self._font_size_ratio,
                align=self._align,
                math=True,
            ).render(RenderContext(height_px=self._height_px))
        except Exception as err:  # noqa: BLE001 - show any render problem inline
            LOG.debug(f"Equation preview failed: {err!r}")
            self._problems.setText(f"⚠  Could not render: {err}")
            return
        # Ink=1 → black on white tape
        img = ImageOps.invert(bitmap.convert("L"))
        pad = 12
        tape = Image.new("L", (img.width + pad * 2, img.height), 255)
        tape.paste(img, (pad, 0))
        self._last_tape = tape
        self._last_width_px = bitmap.width
        self._show_tape()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if getattr(self, "_last_tape", None) is not None:
            self._show_tape()

    def _show_tape(self) -> None:
        tape = self._last_tape
        viewport = self._canvas.viewport()
        avail_w = (viewport.width() if viewport else 600) - 40
        avail_h = (viewport.height() if viewport else 200) - 30
        scale = min(4, avail_w // max(1, tape.width), avail_h // max(1, tape.height))
        scale = max(1, scale)
        pixmap = QPixmap.fromImage(ImageQt.ImageQt(tape.convert("RGBA")))
        pixmap = pixmap.scaled(
            tape.width * scale,
            tape.height * scale,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        )
        self._preview.setPixmap(pixmap)
        self._preview_info.setText(
            f"print resolution, shown ×{scale} · "
            f"≈ {self._last_width_px / PIXELS_PER_MM:.0f} mm"
        )
