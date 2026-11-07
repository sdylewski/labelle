from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from labelle.lib.constants import Direction

LOG = logging.getLogger(__name__)


FOREGROUND_COLOR__VALUES = ["black", "white", "yellow", "blue", "red", "green"]
BACKGROUND_COLOR__VALUES = ["white", "black", "yellow", "blue", "red", "green"]
HORIZONTAL_MARGIN_MM__MAX_VALUE = 100
MIN_LABEL_WIDTH_MM__MIN_VALUE = 300
PREVIEW_SHOW_MARGINS__DEFAULT_VALUE = False
LEAD_IN_MM__MAX_VALUE = 20.0


@dataclass
class Settings:
    background_color: str
    foreground_color: str
    horizontal_margin_mm: float
    justify: Direction
    min_label_width_mm: float
    preview_show_margins: bool
    tape_size_mm: int
    lead_in_mm: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["justify"] = self.justify.value
        return d


class QSettingsToolbar(QWidget):
    """Side panel holding the label/tape settings."""

    settings_changed_signal = QtCore.pyqtSignal(Settings, name="settingsChangedSignal")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._restoring = False
        self._background_color = QComboBox()
        self._foreground_color = QComboBox()
        self._horizontal_margin_mm = QSpinBox()
        self._justify = QComboBox()
        self._min_label_width_mm = QSpinBox()
        self._preview_show_margins = QCheckBox("Show margins in preview")
        self._tape_size_mm = QComboBox()
        self._lead_in_mm = QDoubleSpinBox()

        self._init_elements()
        self._init_connections()
        self._init_layout()
        self.on_settings_changed()

    def _init_elements(self) -> None:
        self._horizontal_margin_mm.setMaximum(HORIZONTAL_MARGIN_MM__MAX_VALUE)
        self._horizontal_margin_mm.setSuffix(" mm")
        self._min_label_width_mm.setMaximum(MIN_LABEL_WIDTH_MM__MIN_VALUE)
        self._min_label_width_mm.setSuffix(" mm")
        self._justify.addItems(d.value for d in Direction)
        self._foreground_color.addItems(FOREGROUND_COLOR__VALUES)
        self._background_color.addItems(BACKGROUND_COLOR__VALUES)
        self._preview_show_margins.setChecked(PREVIEW_SHOW_MARGINS__DEFAULT_VALUE)
        self._lead_in_mm.setRange(0.0, LEAD_IN_MM__MAX_VALUE)
        self._lead_in_mm.setSingleStep(0.5)
        self._lead_in_mm.setDecimals(1)
        self._lead_in_mm.setSuffix(" mm")
        self._lead_in_mm.setToolTip(
            "Blank tape fed before the label starts printing.\n"
            "Prevents a faded or missing first character while the motor spins up.\n"
            "Adds this much to the leading margin."
        )
        self._horizontal_margin_mm.setToolTip(
            "Blank space at each end of the label (minimum is set by the "
            "distance between print head and cutter)."
        )
        self._min_label_width_mm.setToolTip("Pad short labels to at least this length.")

    def update_labeler_context(
        self,
        supported_tape_sizes: tuple[int, ...],
        installed_tape_size: int,
        minimum_horizontal_margin_mm: float,
        lead_in_mm: float = 0.0,
    ) -> None:
        self._restoring = True
        try:
            self._tape_size_mm.clear()
            for tape_size_mm in supported_tape_sizes:
                self._tape_size_mm.addItem(f"{tape_size_mm} mm", tape_size_mm)
            tape_size_index = supported_tape_sizes.index(installed_tape_size)
            self._tape_size_mm.setCurrentIndex(tape_size_index)

            h_margins_mm = round(minimum_horizontal_margin_mm)
            self._horizontal_margin_mm.setMinimum(h_margins_mm)
            if not self._horizontal_margin_mm.value():
                self._horizontal_margin_mm.setValue(h_margins_mm)
            self._min_label_width_mm.setMinimum(h_margins_mm * 2)
            self._lead_in_mm.setValue(lead_in_mm)
        finally:
            self._restoring = False

    def apply_settings(self, values: dict[str, Any]) -> None:
        """Restore settings from a dict (e.g. loaded from preferences)."""
        self._restoring = True
        try:
            for key, combo in (
                ("background_color", self._background_color),
                ("foreground_color", self._foreground_color),
                ("justify", self._justify),
            ):
                if key in values:
                    idx = combo.findText(str(values[key]))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
            if "tape_size_mm" in values:
                try:
                    idx = self._tape_size_mm.findData(int(values["tape_size_mm"]))
                except (TypeError, ValueError):
                    idx = -1
                if idx >= 0:
                    self._tape_size_mm.setCurrentIndex(idx)
            for key, spin in (
                ("horizontal_margin_mm", self._horizontal_margin_mm),
                ("min_label_width_mm", self._min_label_width_mm),
            ):
                if key in values:
                    try:
                        spin.setValue(round(float(values[key])))
                    except (TypeError, ValueError):
                        pass
            if "lead_in_mm" in values:
                try:
                    self._lead_in_mm.setValue(float(values["lead_in_mm"]))
                except (TypeError, ValueError):
                    pass
            if "preview_show_margins" in values:
                v = values["preview_show_margins"]
                if isinstance(v, str):
                    v = v.lower() == "true"
                self._preview_show_margins.setChecked(bool(v))
        finally:
            self._restoring = False
        self.on_settings_changed()

    def _init_connections(self) -> None:
        self._background_color.currentTextChanged.connect(self.on_settings_changed)
        self._foreground_color.currentTextChanged.connect(self.on_settings_changed)
        self._horizontal_margin_mm.valueChanged.connect(self.on_settings_changed)
        self._justify.currentTextChanged.connect(self.on_settings_changed)
        self._min_label_width_mm.valueChanged.connect(self.on_settings_changed)
        self._preview_show_margins.stateChanged.connect(self.on_settings_changed)
        self._tape_size_mm.currentIndexChanged.connect(self.on_settings_changed)
        self._lead_in_mm.valueChanged.connect(self.on_settings_changed)

    def _init_layout(self) -> None:
        tape_box = QGroupBox("Tape")
        tape_form = QFormLayout(tape_box)
        tape_form.addRow("Width:", self._tape_size_mm)
        tape_form.addRow("Text color:", self._foreground_color)
        tape_form.addRow("Tape color:", self._background_color)

        layout_box = QGroupBox("Layout")
        layout_form = QFormLayout(layout_box)
        layout_form.addRow("Margin:", self._horizontal_margin_mm)
        layout_form.addRow("Min length:", self._min_label_width_mm)
        layout_form.addRow("Justify:", self._justify)
        layout_form.addRow(self._preview_show_margins)

        printer_box = QGroupBox("Printer")
        printer_form = QFormLayout(printer_box)
        printer_form.addRow("Lead-in:", self._lead_in_mm)

        layout = QVBoxLayout(self)
        layout.addWidget(tape_box)
        layout.addWidget(layout_box)
        layout.addWidget(printer_box)
        layout.addStretch(1)

    @property
    def settings(self) -> Settings:
        tape_size = self._tape_size_mm.currentData()
        return Settings(
            background_color=self._background_color.currentText(),
            foreground_color=self._foreground_color.currentText(),
            horizontal_margin_mm=self._horizontal_margin_mm.value(),
            justify=Direction(self._justify.currentText()),
            min_label_width_mm=self._min_label_width_mm.value(),
            preview_show_margins=self._preview_show_margins.isChecked(),
            tape_size_mm=tape_size if tape_size is not None else 12,
            lead_in_mm=self._lead_in_mm.value(),
        )

    def on_settings_changed(self, *_args) -> None:
        if self._restoring:
            return
        self.settings_changed_signal.emit(self.settings)
