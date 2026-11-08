from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6 import QtCore
from PyQt6.QtGui import (
    QFont,
    QFontDatabase,
    QIcon,
    QStandardItem,
    QStandardItemModel,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QMenu,
    QMessageBox,
    QToolButton,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labelle.gui.common import crash_msg_box
from labelle.lib.constants import ICON_DIR, BarcodeType, Direction
from labelle.lib.env_config import is_dev_mode_no_margins
from labelle.lib.font_config import get_available_fonts
from labelle.lib.render_engines import (
    BarcodeRenderEngine,
    BarcodeWithTextRenderEngine,
    EmptyRenderEngine,
    NoContentError,
    PicturePathDoesNotExist,
    PictureRenderEngine,
    QrRenderEngine,
    RenderContext,
    RenderEngine,
    TextRenderEngine,
)
from labelle.lib.render_engines.render_engine import RenderEngineException


class FontStyle(QComboBox):
    def __init__(self) -> None:
        super().__init__()

        # Populate font_style
        fonts_model = QStandardItemModel()

        # Create items for all available fonts
        for font_path in get_available_fonts():
            # Create item for font
            item = self.make_combobox_item_for_font(font_path)
            fonts_model.appendRow(item)

        self.setModel(fonts_model)
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(12)

        # Select default font
        self.setCurrentText("Carlito-Regular")

    def make_combobox_item_for_font(self, font_path: Path) -> QStandardItem:
        # Retrieve font data
        font_name = font_path.stem
        font_absolute_path = font_path.absolute()

        # Make combobox item
        item = QStandardItem(font_name)
        item.setData(font_absolute_path, QtCore.Qt.ItemDataRole.UserRole)
        item_font = QFont()

        # Add application font to allow Qt rendering with it
        font_id = QFontDatabase.addApplicationFont(str(font_absolute_path))
        if font_id >= 0:
            loaded_font_families = QFontDatabase.applicationFontFamilies(font_id)
            if loaded_font_families:
                item_font.setFamilies(loaded_font_families)

        # Set bold if font name indictates it
        if "bold" in font_name.lower():
            item_font.setBold(True)

        # Set italic if font name indictates it
        if "italic" in font_name.lower():
            item_font.setItalic(True)

        # font to item
        item.setFont(item_font)

        return item


_OPTIONS_ROW_HEIGHT = 50


def _muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    return label


def _set_combo_text(combo: QComboBox, text: Any) -> None:
    if text is None:
        return
    index = combo.findText(str(text))
    if index >= 0:
        combo.setCurrentIndex(index)


def _set_spin(spin: QSpinBox, value: Any) -> None:
    try:
        spin.setValue(int(value))
    except (TypeError, ValueError):
        pass


# (menu label, text to insert, cursor steps back from end, needs math mode)
MATH_TEMPLATES: list[tuple[str, str, int, bool]] = [
    ("x²   Squared", "^2", 0, True),
    ("x³   Cubed", "^3", 0, True),
    ("xⁿ   Power…", "^{}", 1, True),
    ("x₂   Subscript…", "_{}", 1, True),
    ("√x   Square root…", r"\sqrt{}", 1, True),
    ("∛x   Nth root…", r"\sqrt[3]{}", 1, True),
    ("a⁄b   Fraction…", r"\frac{}{}", 3, True),
]

MATH_SYMBOL_GROUPS: list[tuple[str, str]] = [
    ("Operators", "± ∓ × ÷ · − √ ∛ ∜ ∑ ∏ ∫ ∬ ∮ ∂ ∇ ∞ ∘"),
    ("Relations", "= ≠ ≈ ≡ ∼ ∝ < > ≤ ≥ ≪ ≫"),
    ("Greek", "α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω"),
    ("Super/subscripts", "⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹ ⁺ ⁻ ⁿ ₀ ₁ ₂ ₃ ₄ ₅ ₆ ₇ ₈ ₉ ₊ ₋"),
    ("Fractions", "½ ⅓ ⅔ ¼ ¾ ⅕ ⅛ ⅜ ⅝ ⅞ ‰ %"),
    ("Arrows", "→ ← ↔ ⇒ ⇐ ⇔ ↑ ↓"),
    ("Sets & logic", "∈ ∉ ⊂ ⊃ ⊆ ∪ ∩ ∅ ∀ ∃ ¬ ∧ ∨ ∴ ∵ ℕ ℤ ℚ ℝ ℂ"),
    ("Units & misc", "° ℃ ℉ Ω µ Å ℓ ′ ″ ∠ ⊥ ∥ … ⋯ ℏ"),
]

MATH_HELP = r"""<b>Symbols</b> from the Σ menu work in any text.<br><br>
<b>Math mode</b> (tick “Math”) understands:<br>
<code>x^2</code>, <code>x^10</code>, <code>x^{n+1}</code> — powers<br>
<code>H_2O</code>, <code>a_{ij}</code> — subscripts<br>
<code>\sqrt{2}</code>, <code>\sqrt[3]{x}</code> — roots<br>
<code>\frac{1}{2}</code> — fractions<br>
<code>\pi \pm \times \div \le \ge \ne \approx \infty \deg \sum \int \Delta \Omega \mu</code> … — named symbols<br><br>
Use <code>\^ \_ \{ \} \\</code> for the literal characters."""


class MathSymbolButton(QToolButton):
    """“Σ” button whose menu inserts math symbols and templates."""

    insertRequested = QtCore.pyqtSignal(str, int, bool, name="insertRequested")
    editorRequested = QtCore.pyqtSignal(name="editorRequested")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText("Σ")
        self.setToolTip("Insert a math symbol or formula")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setStyleSheet("QToolButton { font-size: 12pt; padding: 0 8px; }")
        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(self)
        editor_act = menu.addAction("Equation Editor…")
        assert editor_act is not None
        editor_act.triggered.connect(self.editorRequested.emit)
        menu.addSeparator()
        for label, text, back, math in MATH_TEMPLATES:
            act = menu.addAction(label)
            assert act is not None
            act.triggered.connect(
                lambda _=False, t=text, b=back, m=math: self.insertRequested.emit(
                    t, b, m
                )
            )
        menu.addSeparator()
        for title, symbols in MATH_SYMBOL_GROUPS:
            sub = menu.addMenu(title)
            assert sub is not None
            for symbol in symbols.split():
                act = sub.addAction(symbol)
                assert act is not None
                act.triggered.connect(
                    lambda _=False, t=symbol: self.insertRequested.emit(t, 0, False)
                )
        menu.addSeparator()
        help_act = menu.addAction("Math syntax help…")
        assert help_act is not None
        help_act.triggered.connect(
            lambda: QMessageBox.information(self, "Math in labels", MATH_HELP)
        )
        self.setMenu(menu)


class BaseLabelWidget(QWidget):
    """A base class for creating Dymo label widgets.

    Signals:
    --------
    itemRenderSignal : PyQtSignal
        Signal emitted when the content of the label is changed.

    Methods
    -------
    content_changed()
        Emits the itemRenderSignal when the content of the label is changed.
    render_label()
        Abstract method to be implemented by subclasses for rendering the label.

    """

    render_context: RenderContext
    kind: str = "base"

    itemRenderSignal = QtCore.pyqtSignal(name="itemRenderSignal")

    def get_state(self) -> dict[str, Any]:
        """Return a JSON-serializable description of this element."""
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore this element from a dict produced by get_state()."""

    def content_changed(self) -> None:
        """Emit the itemRenderSignal when the content of the label is changed."""
        self.itemRenderSignal.emit()

    @property
    def render_engine_impl(self) -> None:
        """Abstract method for getting the render engine of the label."""
        pass

    @property
    def render_engine(self) -> RenderEngine | None:
        try:
            return self.render_engine_impl
        except RenderEngineException as err:
            crash_msg_box(self, "Render Engine Failed!", err)
            return EmptyRenderEngine()


class TextDymoLabelWidget(BaseLabelWidget):
    """A widget for rendering text on a Dymo label.

    Args:
    ----
        render_context (RenderContext): The rendering context to use.
        parent (QWidget): The parent widget of this widget.

    Attributes:
    ----------
        render_context (RenderContext): The rendering context used by this widget.
        label (QPlainTextEdit): The text label to be rendered on the Dymo label.
        font_style (FontStyle): The font style selection dropdown.
        font_size (QSpinBox): The font size selection spinner.
        frame_width_px (QSpinBox): The frame width selection spinner.
    Signals:
        itemRenderSignal: A signal emitted when the content of the label changes.

    """

    align: QComboBox
    label: QPlainTextEdit
    font_style: FontStyle
    font_size: QSpinBox
    frame_width_px: QSpinBox

    def __init__(self, render_context: RenderContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.render_context = render_context

        default_label_text = "." if is_dev_mode_no_margins() else "text"
        self.label = QPlainTextEdit(default_label_text)
        self.label.setFixedHeight(max(52, 15 * (len(self.label.toPlainText().splitlines()) + 2)))
        self.setFixedHeight(self.label.height() + _OPTIONS_ROW_HEIGHT)
        self.font_style = FontStyle()
        self.font_size = QSpinBox()
        self.font_size.setMaximum(150)
        self.font_size.setMinimum(0)
        self.font_size.setSingleStep(1)
        self.font_size.setValue(90)
        self.frame_width_px = QSpinBox()
        self.align = QComboBox()
        self.math = QCheckBox("Math")
        self.math.setToolTip(
            "Interpret x^2, H_2O, \\sqrt{x}, \\frac{a}{b}, \\pi … "
            "(see Σ → Math syntax help)"
        )
        self.symbol_button = MathSymbolButton()
        self.symbol_button.insertRequested.connect(self._insert_math)
        self.symbol_button.editorRequested.connect(self.open_equation_editor)

        self.align.addItems(["left", "center", "right"])

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)
        item_icon = QLabel()
        item_icon.setPixmap(QIcon(str(ICON_DIR / "txt_icon.png")).pixmap(32, 32))
        item_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        self.item_icon = item_icon
        options = QHBoxLayout()
        for text, widget in (
            ("Font", self.font_style),
            ("Size", self.font_size),
            ("Frame", self.frame_width_px),
            ("Align", self.align),
        ):
            options.addWidget(_muted_label(text))
            options.addWidget(widget)
        options.addStretch(1)
        for spin in (self.font_size, self.frame_width_px):
            spin.setMaximumWidth(80)
        self.font_size.setSuffix(" %")
        self.frame_width_px.setSuffix(" px")
        body = QVBoxLayout()
        body.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(self.label, 1)
        math_tools = QVBoxLayout()
        self.math_tools = math_tools
        math_tools.setSpacing(2)
        math_tools.addWidget(self.symbol_button)
        math_tools.addWidget(self.math)
        math_tools.addStretch(1)
        top.addLayout(math_tools)
        body.addLayout(top)
        body.addLayout(options)
        layout.addWidget(item_icon, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body, 1)
        self.label.textChanged.connect(self.content_changed)
        self.frame_width_px.valueChanged.connect(self.content_changed)
        self.font_size.valueChanged.connect(self.content_changed)
        self.font_style.currentTextChanged.connect(self.content_changed)
        self.align.currentTextChanged.connect(self.content_changed)
        self.math.stateChanged.connect(self.content_changed)
        self.setLayout(layout)

    kind = "text"

    def open_equation_editor(self) -> bool:
        """Edit this element's text in the equation editor. True if accepted."""
        from labelle.gui.q_equation_editor import EquationEditorDialog

        dialog = EquationEditorDialog(
            source=self.label.toPlainText(),
            font_path=str(self.font_style.currentData()),
            font_size_ratio=self.font_size.value() / 100.0,
            height_px=self.render_context.height_px,
            align=Direction(self.align.currentText()),
            parent=self.window(),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return False
        self.label.setPlainText(dialog.source())
        self.math.setChecked(True)
        return True

    def _insert_math(self, text: str, cursor_back: int, needs_math: bool) -> None:
        cursor = self.label.textCursor()
        cursor.insertText(text)
        if cursor_back:
            cursor.movePosition(
                cursor.MoveOperation.Left, cursor.MoveMode.MoveAnchor, cursor_back
            )
        self.label.setTextCursor(cursor)
        if needs_math and not self.math.isChecked():
            self.math.setChecked(True)
        self.label.setFocus()

    def get_state(self) -> dict[str, Any]:
        return {
            "text": self.label.toPlainText(),
            "font": self.font_style.currentText(),
            "font_size": self.font_size.value(),
            "frame_width_px": self.frame_width_px.value(),
            "align": self.align.currentText(),
            "math": self.math.isChecked(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.label.setPlainText(str(state.get("text", "")))
        _set_combo_text(self.font_style, state.get("font"))
        _set_spin(self.font_size, state.get("font_size", 90))
        _set_spin(self.frame_width_px, state.get("frame_width_px", 0))
        _set_combo_text(self.align, state.get("align"))
        self.math.setChecked(bool(state.get("math", False)))

    def content_changed(self) -> None:
        """Manage changes to the label contents.

        In particular, update the height of the label and emit the itemRenderSignal
        when the content of the label changes.
        """
        self.label.setFixedHeight(max(52, 15 * (len(self.label.toPlainText().splitlines()) + 2)))
        self.setFixedHeight(self.label.height() + _OPTIONS_ROW_HEIGHT)
        self.itemRenderSignal.emit()

    @property
    def render_engine_impl(self):
        """Get the render engine for the text label using the current settings.

        Returns
        -------
            TextRenderEngine: The rendered engine.

        """
        selected_alignment = Direction(self.align.currentText())
        return TextRenderEngine(
            text_lines=self.label.toPlainText().splitlines(),
            font_file_name=self.font_style.currentData(),
            frame_width_px=self.frame_width_px.value(),
            font_size_ratio=self.font_size.value() / 100.0,
            align=selected_alignment,
            math=self.math.isChecked(),
        )


class QrDymoLabelWidget(BaseLabelWidget):
    """A widget for rendering QR codes on Dymo labels.

    Args:
    ----
        render_context (RenderContext): The render context to use for rendering
            the QR code.
        parent (QWidget, optional): The parent widget. Defaults to None.

    """

    def __init__(self, render_context, parent=None):
        """Initialize the QrDymoLabelWidget.

        Args:
        ----
            render_context (RenderContext): The render context to use for rendering
                the QR code.
            parent (QWidget, optional): The parent widget. Defaults to None.

        """
        super().__init__(parent)
        self.render_context = render_context

        self.label = QLineEdit("")
        self.label.setPlaceholderText("QR code content (URL, text…)")
        layout = QHBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)
        item_icon = QLabel()
        item_icon.setPixmap(QIcon(str(ICON_DIR / "qr_icon.png")).pixmap(32, 32))
        item_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(item_icon)
        layout.addWidget(self.label, 1)
        self.label.textChanged.connect(self.content_changed)
        self.setLayout(layout)

    kind = "qr"

    def get_state(self) -> dict[str, Any]:
        return {"text": self.label.text()}

    def set_state(self, state: dict[str, Any]) -> None:
        self.label.setText(str(state.get("text", "")))

    @property
    def render_engine_impl(self):
        """Get the render engine for the QR label using the current settings.

        Returns
        -------
            QrRenderEngine: The render engine.

        """
        try:
            return QrRenderEngine(content=self.label.text())
        except NoContentError:
            return EmptyRenderEngine()


class BarcodeDymoLabelWidget(BaseLabelWidget):
    """A widget for rendering barcode labels using the Dymo label printer.

    Args:
    ----
        render_context (RenderContext): An instance of the RenderContext class.
        parent (QWidget): The parent widget of this widget.

    Attributes:
    ----------
        render_context (RenderContext): An instance of the RenderContext class.
        label (QLineEdit): A QLineEdit widget for entering the content of the
            barcode label.
        Type (QComboBox): A QComboBox widget for selecting the type of barcode
            to render.
        font_style (FontStyle): The font style selection dropdown.
        font_size (QSpinBox): The font size selection spinner.
        frame_width_px (QSpinBox): The frame width selection spinner.
    Signals:
        content_changed(): Emitted when the content of the label or the selected
            barcode type changes.

    Methods:
    -------
        __init__(self, render_context, parent=None): Initializes the widget.
        render_label_impl(self): Renders the barcode label using the current content
            and barcode type.

    """

    label: QLineEdit
    barcode_type_label: QLabel
    barcode_type: QComboBox
    show_text_label: QLabel
    show_text_checkbox: QCheckBox
    font_style: FontStyle
    font_size: QSpinBox
    frame_width_px: QSpinBox
    font_label: QLabel
    size_label: QLabel
    frame_label: QLabel
    align_label: QLabel
    align: QComboBox

    def __init__(self, render_context, parent=None):
        super().__init__(parent)
        self.render_context = render_context

        self.label = QLineEdit("")

        # Hidable text fields and their labels
        self.font_label = QLabel("Font:")
        self.font_style = FontStyle()
        self.size_label = QLabel("Size [%]:")
        self.font_size = QSpinBox()
        self.font_size.setMaximum(150)
        self.font_size.setMinimum(0)
        self.font_size.setSingleStep(1)
        self.font_size.setValue(90)
        self.frame_label = QLabel("Frame Width:")
        self.frame_width_px = QSpinBox()
        self.align_label = QLabel("Alignment:")
        self.align = QComboBox()
        self.item_icon = QLabel()
        self.item_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        self.align.addItems(["left", "center", "right"])
        # Set the default value to "center"
        self.align.setCurrentIndex(1)

        self.set_text_fields_visibility(True)

        layout = QHBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)

        self.label.setPlaceholderText("Barcode content")
        self.barcode_type_label = QLabel("Type:")
        self.barcode_type = QComboBox()
        self.barcode_type.addItems(bt.value for bt in BarcodeType)

        # Checkbox for toggling text fields
        self.show_text_label = QLabel("Text:")
        self.show_text_checkbox = QCheckBox()
        self.show_text_checkbox.setChecked(True)
        self.show_text_checkbox.stateChanged.connect(
            self.toggle_text_fields_and_rerender
        )

        self.show_text_checkbox.setText("Show text")
        self.show_text_label.setVisible(False)
        self.font_size.setSuffix(" %")
        self.frame_width_px.setSuffix(" px")
        for lbl, text in (
            (self.barcode_type_label, "Type"),
            (self.font_label, "Font"),
            (self.size_label, "Size"),
            (self.frame_label, "Frame"),
            (self.align_label, "Align"),
        ):
            lbl.setText(text)
            lbl.setObjectName("muted")
        top = QHBoxLayout()
        top.addWidget(self.label, 1)
        top.addWidget(self.barcode_type_label)
        top.addWidget(self.barcode_type)
        top.addWidget(self.show_text_checkbox)
        options = QHBoxLayout()
        for widget in (
            self.font_label, self.font_style, self.size_label, self.font_size,
            self.frame_label, self.frame_width_px, self.align_label, self.align,
        ):
            options.addWidget(widget)
        options.addStretch(1)
        body = QVBoxLayout()
        body.setSpacing(4)
        body.addLayout(top)
        body.addLayout(options)
        layout.addWidget(self.item_icon, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body, 1)

        self.label.textChanged.connect(self.content_changed)
        self.frame_width_px.valueChanged.connect(self.content_changed)
        self.font_size.valueChanged.connect(self.content_changed)
        self.font_style.currentTextChanged.connect(self.content_changed)
        self.align.currentTextChanged.connect(self.content_changed)
        self.barcode_type.currentTextChanged.connect(self.content_changed)

        self.setLayout(layout)

    kind = "barcode"

    def get_state(self) -> dict[str, Any]:
        return {
            "text": self.label.text(),
            "barcode_type": self.barcode_type.currentText(),
            "show_text": self.show_text_checkbox.isChecked(),
            "font": self.font_style.currentText(),
            "font_size": self.font_size.value(),
            "frame_width_px": self.frame_width_px.value(),
            "align": self.align.currentText(),
        }

    def set_state(self, state: dict[str, Any]) -> None:
        self.label.setText(str(state.get("text", "")))
        _set_combo_text(self.barcode_type, state.get("barcode_type"))
        self.show_text_checkbox.setChecked(bool(state.get("show_text", True)))
        _set_combo_text(self.font_style, state.get("font"))
        _set_spin(self.font_size, state.get("font_size", 90))
        _set_spin(self.frame_width_px, state.get("frame_width_px", 0))
        _set_combo_text(self.align, state.get("align"))

    def set_text_fields_visibility(self, visible):
        self.font_label.setVisible(visible)
        self.font_style.setVisible(visible)
        self.size_label.setVisible(visible)
        self.font_size.setVisible(visible)
        self.frame_label.setVisible(visible)
        self.frame_width_px.setVisible(visible)
        self.align_label.setVisible(visible)
        self.align.setVisible(visible)
        if visible:
            self.item_icon.setPixmap(
                QIcon(str(ICON_DIR / "barcode_text_icon.png")).pixmap(32, 32)
            )
        else:
            self.item_icon.setPixmap(
                QIcon(str(ICON_DIR / "barcode_icon.png")).pixmap(32, 32)
            )

    def toggle_text_fields_and_rerender(self) -> None:
        is_checked = self.show_text_checkbox.isChecked()
        self.set_text_fields_visibility(is_checked)
        self.content_changed()  # Trigger rerender

    @property
    def render_engine_impl(self):
        """Get the render engine for the barcode label using the current settings.

        Returns
        -------
            RenderEngine: The rendered engine (either BarcodeRenderEngine or
            BarcodeWithTextRenderEngine).

        """
        render_engine: RenderEngine
        if self.show_text_checkbox.isChecked():
            render_engine = BarcodeWithTextRenderEngine(
                content=self.label.text(),
                barcode_type=self.barcode_type.currentText(),
                font_file_name=self.font_style.currentData(),
                frame_width_px=self.frame_width_px.value(),
                font_size_ratio=self.font_size.value() / 100.0,
                align=Direction(self.align.currentText()),
            )
        else:
            render_engine = BarcodeRenderEngine(
                content=self.label.text(),
                barcode_type=self.barcode_type.currentText(),
            )
        return render_engine


class ImageDymoLabelWidget(BaseLabelWidget):
    """A widget for rendering image-based Dymo labels.

    Args:
    ----
        context (RenderContext): The render context to use for rendering the label.
        parent (QWidget, optional): The parent widget. Defaults to None.

    """

    def __init__(self, render_context, parent=None):
        """Initialize the ImageDymoLabelWidget.

        Args:
        ----
            render_context (RenderContext): The render context to use for rendering
                the label.
            parent (QWidget, optional): The parent widget. Defaults to None.

        """
        super().__init__(parent)
        self.render_context = render_context

        self.label = QLineEdit("")
        layout = QHBoxLayout()
        layout.setContentsMargins(6, 4, 6, 4)
        item_icon = QLabel()
        self.label.setPlaceholderText("Path to an image file")
        item_icon.setPixmap(QIcon(str(ICON_DIR / "img_icon.png")).pixmap(32, 32))
        item_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter)

        button = QPushButton("Browse…")
        button.clicked.connect(self._choose_file)

        layout.addWidget(item_icon)
        layout.addWidget(self.label, 1)
        layout.addWidget(button)

        self.label.textChanged.connect(self.content_changed)
        self.setLayout(layout)

    kind = "image"

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select image", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.svg);;All files (*)"
        )
        if path:
            self.label.setText(str(Path(path).absolute()))

    def get_state(self) -> dict[str, Any]:
        return {"path": self.label.text()}

    def set_state(self, state: dict[str, Any]) -> None:
        self.label.setText(str(state.get("path", "")))

    @property
    def render_engine_impl(self):
        """Get the render engine for the image label using the current settings.

        Returns
        -------
            PictureRenderEngine: The rendered engine.

        """
        try:
            return PictureRenderEngine(picture_path=self.label.text())
        except PicturePathDoesNotExist:
            return EmptyRenderEngine()


class EquationDymoLabelWidget(TextDymoLabelWidget):
    """A text element that is always in math mode, edited with the equation editor."""

    kind = "math"
    DEFAULT_SOURCE = "x^2"

    def __init__(self, render_context: RenderContext, parent: QWidget | None = None):
        super().__init__(render_context, parent)
        self.math.setChecked(True)
        self.math.setVisible(False)
        self.symbol_button.setVisible(False)
        self.item_icon.setPixmap(QIcon(str(ICON_DIR / "math_icon.png")).pixmap(32, 32))
        self.item_icon.setToolTip("Equation")
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.label.setFont(mono)
        self.label.setToolTip("LaTeX-like source — click “Edit…” for the equation editor")
        self.label.setPlainText(self.DEFAULT_SOURCE)
        self.edit_button = QPushButton("Edit…")
        self.edit_button.setToolTip("Open the equation editor")
        self.edit_button.clicked.connect(self.open_equation_editor)
        self.math_tools.insertWidget(0, self.edit_button)

    def set_state(self, state: dict[str, Any]) -> None:
        super().set_state(state)
        self.math.setChecked(True)

    def get_state(self) -> dict[str, Any]:
        state = super().get_state()
        state.pop("math", None)
        return state


LABEL_WIDGET_CLASSES: dict[str, type[BaseLabelWidget]] = {
    cls.kind: cls
    for cls in (
        TextDymoLabelWidget,
        EquationDymoLabelWidget,
        QrDymoLabelWidget,
        BarcodeDymoLabelWidget,
        ImageDymoLabelWidget,
    )
}
