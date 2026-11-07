"""Modern light/dark look for labelle-gui (Fusion style + stylesheet)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory

THEMES = ("system", "light", "dark")

_LIGHT = {
    "window": "#f4f5f7",
    "surface": "#ffffff",
    "surface_alt": "#f8f9fb",
    "canvas": "#e6e8ec",
    "border": "#dcdfe4",
    "text": "#1f2329",
    "muted": "#6b7280",
    "accent": "#2f6fed",
    "accent_hover": "#2559c4",
    "accent_text": "#ffffff",
    "hover": "#eceef2",
    "selection": "#dbe6fd",
    "danger": "#d64545",
}

_DARK = {
    "window": "#1e1f22",
    "surface": "#2a2c30",
    "surface_alt": "#26282b",
    "canvas": "#17181a",
    "border": "#3a3d42",
    "text": "#e6e7ea",
    "muted": "#9aa0a8",
    "accent": "#4c8dff",
    "accent_hover": "#6aa0ff",
    "accent_text": "#ffffff",
    "hover": "#34373c",
    "selection": "#2d4166",
    "danger": "#ef6b6b",
}


def system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    if hints is not None and hasattr(hints, "colorScheme"):
        return hints.colorScheme() == Qt.ColorScheme.Dark
    return False


def resolve(theme: str) -> str:
    if theme not in THEMES:
        theme = "system"
    if theme == "system":
        return "dark" if system_prefers_dark() else "light"
    return theme


def colors(theme: str) -> dict[str, str]:
    return _DARK if resolve(theme) == "dark" else _LIGHT


def _palette(c: dict[str, str]) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    p.setColor(role.Window, QColor(c["window"]))
    p.setColor(role.WindowText, QColor(c["text"]))
    p.setColor(role.Base, QColor(c["surface"]))
    p.setColor(role.AlternateBase, QColor(c["surface_alt"]))
    p.setColor(role.Text, QColor(c["text"]))
    p.setColor(role.Button, QColor(c["surface"]))
    p.setColor(role.ButtonText, QColor(c["text"]))
    p.setColor(role.ToolTipBase, QColor(c["surface"]))
    p.setColor(role.ToolTipText, QColor(c["text"]))
    p.setColor(role.PlaceholderText, QColor(c["muted"]))
    p.setColor(role.Highlight, QColor(c["accent"]))
    p.setColor(role.HighlightedText, QColor(c["accent_text"]))
    p.setColor(role.Link, QColor(c["accent"]))
    for r in (role.WindowText, role.Text, role.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, r, QColor(c["muted"]))
    return p


def _stylesheet(c: dict[str, str]) -> str:
    return f"""
QMainWindow, QDialog {{ background: {c["window"]}; }}
QWidget {{ font-size: 10pt; }}
QToolTip {{
    background: {c["surface"]}; color: {c["text"]};
    border: 1px solid {c["border"]}; padding: 4px 6px; border-radius: 4px;
}}

/* Toolbars */
QToolBar {{
    background: {c["surface"]}; border: none;
    border-bottom: 1px solid {c["border"]}; padding: 4px 6px; spacing: 2px;
}}
QToolBar::separator {{ background: {c["border"]}; width: 1px; margin: 6px 6px; }}
QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    padding: 4px 8px; color: {c["text"]};
}}
QToolButton:hover {{ background: {c["hover"]}; }}
QToolButton:pressed {{ background: {c["selection"]}; }}
QToolButton:disabled {{ color: {c["muted"]}; }}

/* Primary print button */
QPushButton#printButton {{
    background: {c["accent"]}; color: {c["accent_text"]}; border: none;
    border-radius: 8px; padding: 8px 22px; font-weight: 600; font-size: 11pt;
}}
QPushButton#printButton:hover {{ background: {c["accent_hover"]}; }}
QPushButton#printButton:disabled {{ background: {c["border"]}; color: {c["muted"]}; }}

QPushButton {{
    background: {c["surface"]}; color: {c["text"]};
    border: 1px solid {c["border"]}; border-radius: 6px; padding: 5px 12px;
}}
QPushButton:hover {{ background: {c["hover"]}; }}
QPushButton:disabled {{ color: {c["muted"]}; }}

/* Inputs */
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {c["surface"]}; color: {c["text"]};
    border: 1px solid {c["border"]}; border-radius: 6px; padding: 3px 6px;
    selection-background-color: {c["accent"]};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {c["accent"]}; }}
QComboBox {{ padding-right: 20px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    border: none; width: 20px;
}}
QComboBox::down-arrow, QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({c["_arrow_down"]}); width: 10px; height: 10px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({c["_arrow_up"]}); width: 10px; height: 10px;
}}
QCheckBox::indicator:checked {{ image: url({c["_check"]}); }}
QSpinBox, QDoubleSpinBox {{ padding-right: 18px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; border: none; background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; border: none; background: transparent;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {c["hover"]};
}}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {c["border"]};
    border-radius: 4px; background: {c["surface"]};
}}
QCheckBox::indicator:checked {{ background: {c["accent"]}; border-color: {c["accent"]}; }}
QToolButton#zoomButton {{ font-size: 12pt; min-width: 26px; padding: 0 6px; }}
QComboBox QAbstractItemView {{
    background: {c["surface"]}; border: 1px solid {c["border"]};
    selection-background-color: {c["selection"]}; selection-color: {c["text"]};
}}

/* Cards */
QGroupBox {{
    background: {c["surface"]}; border: 1px solid {c["border"]};
    border-radius: 8px; margin-top: 14px; padding: 10px 8px 6px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px;
    color: {c["muted"]}; font-weight: 600;
}}
QFrame#card {{
    background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 10px;
}}
QLabel#sectionTitle {{ color: {c["muted"]}; font-weight: 600; }}
QLabel#muted {{ color: {c["muted"]}; }}

/* Preview canvas */
QScrollArea#previewCanvas, QWidget#previewCanvasInner {{
    background: {c["canvas"]}; border: none; border-radius: 10px;
}}

/* Lists */
QListWidget {{
    background: {c["surface"]}; border: 1px solid {c["border"]};
    border-radius: 8px; padding: 4px; outline: none;
}}
QListWidget::item {{ border-radius: 6px; padding: 2px; margin: 1px 0; }}
QListWidget::item:alternate {{ background: {c["surface_alt"]}; }}
QListWidget::item:hover {{ background: {c["hover"]}; }}
QListWidget::item:selected {{ background: {c["selection"]}; color: {c["text"]}; }}

/* Docks */
QDockWidget {{ color: {c["muted"]}; font-weight: 600; }}
QDockWidget::title {{
    background: {c["window"]}; padding: 6px 8px; text-align: left;
}}

/* Menus / status */
QMenuBar {{ background: {c["surface"]}; border-bottom: 1px solid {c["border"]}; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {c["hover"]}; }}
QMenu {{
    background: {c["surface"]}; border: 1px solid {c["border"]};
    border-radius: 6px; padding: 4px;
}}
QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c["selection"]}; color: {c["text"]}; }}
QMenu::separator {{ height: 1px; background: {c["border"]}; margin: 4px 8px; }}
QStatusBar {{
    background: {c["surface"]}; border-top: 1px solid {c["border"]};
    color: {c["muted"]};
}}
QStatusBar::item {{ border: none; }}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent; border: none; margin: 0;
}}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle {{ background: {c["border"]}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {c["muted"]}; }}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}
"""


_SVGS = {
    "_arrow_down": '<path d="M2 4 L6 8 L10 4" />',
    "_arrow_up": '<path d="M2 8 L6 4 L10 8" />',
    "_check": '<path d="M2.5 6.5 L5 9 L9.5 3.5" />',
}


def _icon_files(c: dict[str, str]) -> dict[str, str]:
    """Write tiny SVG icons in the theme colors; QSS needs them as files."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericCacheLocation
    )
    folder = Path(base) / "labelle" / "gui-icons"
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for key, path_d in _SVGS.items():
        color = c["accent_text"] if key == "_check" else c["muted"]
        f = folder / f"{key.strip('_')}-{color.strip('#')}.svg"
        if not f.exists():
            f.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" '
                f'viewBox="0 0 12 12"><g fill="none" stroke="{color}" '
                'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
                f"{path_d}</g></svg>"
            )
        out[key] = f.as_posix()
    return out


def apply_theme(app: QApplication, theme: str) -> dict[str, str]:
    """Apply the theme; returns the resolved color dict."""
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)
    c = dict(colors(theme))
    c.update(_icon_files(c))
    app.setPalette(_palette(c))
    app.setStyleSheet(_stylesheet(c))
    return c
