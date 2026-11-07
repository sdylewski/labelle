from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from PIL import Image
from PyQt6 import QtCore
from PyQt6.QtCore import QCommandLineOption, QCommandLineParser, Qt
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from labelle import __version__
from labelle.gui.common import crash_msg_box
from labelle.gui.label_store import (
    LABEL_FILE_SUFFIX,
    LABEL_SETTING_KEYS,
    LabelDocument,
    label_name_for_path,
    library_dir,
    path_for_label_name,
    preferences,
)
from labelle.gui.q_device_selector import QDeviceSelector
from labelle.gui.q_label_library import QLabelLibrary
from labelle.gui.q_labels_list import QLabelList
from labelle.gui.q_render import QRender
from labelle.gui.q_settings_toolbar import QSettingsToolbar, Settings
from labelle.gui.theme import THEMES, apply_theme
from labelle.lib.constants import ICON_DIR, PIXELS_PER_MM
from labelle.lib.devices.dymo_labeler import DymoLabeler, DymoLabelerPrintError
from labelle.lib.env_config import is_verbose_env_vars
from labelle.lib.logger import configure_logging, set_not_verbose
from labelle.lib.render_engines import RenderContext
from labelle.lib.utils import system_run

LOG = logging.getLogger(__name__)

UNTITLED = "Untitled"


def _icon(theme_name: str, fallback: QStyle.StandardPixmap | None = None) -> QIcon:
    icon = QIcon.fromTheme(theme_name)
    if icon.isNull() and fallback is not None:
        style = QApplication.style()
        if style is not None:
            icon = style.standardIcon(fallback)
    return icon


class LabelleWindow(QMainWindow):
    _label_bitmap_to_print: Image.Image | None
    _dymo_labeler: DymoLabeler
    _render_context: RenderContext

    def __init__(self) -> None:
        super().__init__()
        self._label_bitmap_to_print = None
        self._prefs = preferences()
        self._current_path: Path | None = None
        self._doc_name = UNTITLED
        self._dirty = False
        self._loading = False
        self._last_label_settings: dict | None = None

        self._dymo_labeler = DymoLabeler()
        self._device_selector = QDeviceSelector(self)
        self._label_list = QLabelList()
        self._render = QRender()
        self._settings_panel = QSettingsToolbar()
        self._library = QLabelLibrary()

        self._init_window()
        self._init_actions()
        self._init_menus()
        self._init_toolbars()
        self._init_central()
        self._init_docks()
        self._init_statusbar()

        self._settings_panel.update_labeler_context(
            supported_tape_sizes=self._dymo_labeler.SUPPORTED_TAPE_SIZES_MM,
            installed_tape_size=self._dymo_labeler.tape_size_mm,
            minimum_horizontal_margin_mm=self._dymo_labeler.minimum_horizontal_margin_mm,
            lead_in_mm=self._dymo_labeler.lead_in_mm,
        )
        self._init_connections()
        self._restore_preferences()
        self._device_selector.repopulate()
        self._update_title()

    # ------------------------------------------------------------------ setup

    def _init_window(self) -> None:
        self.setWindowIcon(QIcon(str(ICON_DIR / "logo_small.png")))
        self.resize(1280, 760)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
        )

    def _action(
        self,
        text: str,
        slot,
        shortcut: QKeySequence | QKeySequence.StandardKey | str | None = None,
        icon: QIcon | None = None,
        tip: str | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if icon is not None:
            action.setIcon(icon)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        action.triggered.connect(slot)
        return action

    def _init_actions(self) -> None:
        sp = QStyle.StandardPixmap
        K = QKeySequence.StandardKey
        self.act_new = self._action(
            "&New", self._on_new, K.New, _icon("document-new", sp.SP_FileIcon),
            "Start a new label",
        )
        self.act_import = self._action(
            "&Open File…", self._on_import, K.Open,
            _icon("document-open", sp.SP_DialogOpenButton),
            "Open a label file from anywhere",
        )
        self.act_save = self._action(
            "&Save", self._on_save, K.Save,
            _icon("document-save", sp.SP_DialogSaveButton),
            "Save this label to your library",
        )
        self.act_save_as = self._action(
            "Save &As…", self._on_save_as, K.SaveAs,
            _icon("document-save-as", sp.SP_DialogSaveButton),
            "Save a copy under a new name",
        )
        self.act_export = self._action(
            "&Export to File…", self._on_export, None,
            _icon("document-export"), "Save the label design to a file of your choice",
        )
        self.act_export_png = self._action(
            "Export &Image…", self._on_export_png, None, _icon("image-x-generic"),
            "Save the preview as a PNG image",
        )
        self.act_print = self._action(
            "&Print", self._on_print_label, K.Print,
            _icon("document-print", sp.SP_DialogApplyButton), "Print the label",
        )
        self.act_quit = self._action("&Quit", self.close, K.Quit, _icon("application-exit"))

        self.act_add_text = self._action(
            "Text", lambda: self._add_element("text"), "Ctrl+T",
            QIcon(str(ICON_DIR / "txt_icon.png")), "Add a text element (Ctrl+T)",
        )
        self.act_add_qr = self._action(
            "QR Code", lambda: self._add_element("qr"), "Ctrl+Shift+Q",
            QIcon(str(ICON_DIR / "qr_icon.png")), "Add a QR code",
        )
        self.act_add_barcode = self._action(
            "Barcode", lambda: self._add_element("barcode"), "Ctrl+B",
            QIcon(str(ICON_DIR / "barcode_icon.png")), "Add a barcode (Ctrl+B)",
        )
        self.act_add_image = self._action(
            "Image", lambda: self._add_element("image"), "Ctrl+I",
            QIcon(str(ICON_DIR / "img_icon.png")), "Add an image (Ctrl+I)",
        )
        self.act_remove = self._action(
            "Remove", self._label_list.remove_selected, None,
            _icon("list-remove", sp.SP_TrashIcon), "Remove the selected element (Del)",
        )

        self.act_zoom_in = self._action(
            "Zoom &In", lambda: self._set_zoom(self._render.zoom + 0.5), K.ZoomIn,
            _icon("zoom-in"),
        )
        self.act_zoom_out = self._action(
            "Zoom &Out", lambda: self._set_zoom(self._render.zoom - 0.5), K.ZoomOut,
            _icon("zoom-out"),
        )
        self.act_zoom_reset = self._action(
            "&Actual Size", lambda: self._set_zoom(1.0), "Ctrl+0",
            _icon("zoom-original"),
        )

        self._theme_group = QActionGroup(self)
        self._theme_actions: dict[str, QAction] = {}
        for theme in THEMES:
            act = QAction(theme.capitalize(), self, checkable=True)
            act.triggered.connect(lambda _=False, t=theme: self._set_theme(t))
            self._theme_group.addAction(act)
            self._theme_actions[theme] = act

    def _init_menus(self) -> None:
        bar = self.menuBar()
        assert bar is not None
        file_menu = bar.addMenu("&File")
        assert file_menu is not None
        for a in (self.act_new, self.act_import, None, self.act_save,
                  self.act_save_as, self.act_export, self.act_export_png, None,
                  self.act_print, None, self.act_quit):
            file_menu.addSeparator() if a is None else file_menu.addAction(a)

        insert_menu = bar.addMenu("&Insert")
        assert insert_menu is not None
        for a in (self.act_add_text, self.act_add_qr, self.act_add_barcode,
                  self.act_add_image, None, self.act_remove):
            insert_menu.addSeparator() if a is None else insert_menu.addAction(a)

        self._view_menu = bar.addMenu("&View")
        assert self._view_menu is not None
        for a in (self.act_zoom_in, self.act_zoom_out, self.act_zoom_reset):
            self._view_menu.addAction(a)
        self._view_menu.addSeparator()
        theme_menu = self._view_menu.addMenu("&Theme")
        assert theme_menu is not None
        for act in self._theme_actions.values():
            theme_menu.addAction(act)
        self._view_menu.addSeparator()

        help_menu = bar.addMenu("&Help")
        assert help_menu is not None
        help_menu.addAction("Open Labels Folder", self._open_library_folder)
        help_menu.addAction("&About Labelle", self._on_about)

    def _init_toolbars(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QtCore.QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.addAction(self.act_new)
        tb.addAction(self.act_save)
        tb.addSeparator()
        add_label = QLabel(" Add: ")
        add_label.setObjectName("muted")
        tb.addWidget(add_label)
        for a in (self.act_add_text, self.act_add_qr, self.act_add_barcode,
                  self.act_add_image):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.act_remove)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        printer_label = QLabel("Printer: ")
        printer_label.setObjectName("muted")
        tb.addWidget(printer_label)
        self._device_selector.setStyleSheet("QToolBar { border: none; padding: 0; }")
        tb.addWidget(self._device_selector)
        self.addToolBar(tb)
        self._main_toolbar = tb

    def _init_central(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)

        # --- Preview card
        preview_card = QFrame()
        preview_card.setObjectName("card")
        pv = QVBoxLayout(preview_card)
        pv.setContentsMargins(14, 10, 14, 14)

        header = QHBoxLayout()
        title = QLabel("Preview")
        title.setObjectName("sectionTitle")
        self._length_label = QLabel("")
        self._length_label.setObjectName("muted")
        header.addWidget(title)
        header.addSpacing(8)
        header.addWidget(self._length_label)
        header.addStretch(1)
        for text, act in (("−", self.act_zoom_out), (None, self.act_zoom_reset),
                          ("+", self.act_zoom_in)):
            b = QToolButton()
            b.setObjectName("zoomButton")
            b.setAutoRaise(True)
            b.setToolTip(act.text().replace("&", ""))
            if text is None:
                b.setDefaultAction(act)
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            else:
                b.setText(text)
                b.clicked.connect(act.trigger)
            header.addWidget(b)
        pv.addLayout(header)

        self._canvas = QScrollArea()
        self._canvas.setObjectName("previewCanvas")
        self._canvas.setWidgetResizable(True)
        self._canvas.setMinimumHeight(170)
        inner = QWidget()
        inner.setObjectName("previewCanvasInner")
        il = QVBoxLayout(inner)
        il.setContentsMargins(24, 24, 24, 24)
        il.addWidget(self._render, alignment=Qt.AlignmentFlag.AlignCenter)
        self._canvas.setWidget(inner)
        pv.addWidget(self._canvas, 1)

        footer = QHBoxLayout()
        self._printer_hint = QLabel("")
        self._printer_hint.setObjectName("muted")
        footer.addWidget(self._printer_hint)
        footer.addStretch(1)
        footer.addWidget(QLabel("Copies:"))
        self._copies = QSpinBox()
        self._copies.setRange(1, 99)
        footer.addWidget(self._copies)
        footer.addSpacing(8)
        self._print_button = QPushButton("  Print")
        self._print_button.setObjectName("printButton")
        self._print_button.setIcon(_icon("document-print"))
        self._print_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._print_button.setToolTip("Print (Ctrl+P)")
        self._print_button.clicked.connect(self._on_print_label)
        footer.addWidget(self._print_button)
        pv.addLayout(footer)

        # --- Elements card
        elements_card = QFrame()
        elements_card.setObjectName("card")
        ev = QVBoxLayout(elements_card)
        ev.setContentsMargins(14, 10, 14, 14)
        eh = QHBoxLayout()
        etitle = QLabel("Elements")
        etitle.setObjectName("sectionTitle")
        ehint = QLabel("Drag to reorder · right-click for more")
        ehint.setObjectName("muted")
        eh.addWidget(etitle)
        eh.addStretch(1)
        eh.addWidget(ehint)
        ev.addLayout(eh)
        ev.addWidget(self._label_list, 1)

        outer.addWidget(preview_card, 2)
        outer.addWidget(elements_card, 3)
        self.setCentralWidget(central)

    def _init_docks(self) -> None:
        lib_dock = QDockWidget("Saved Labels", self)
        lib_dock.setObjectName("libraryDock")
        lib_dock.setWidget(self._library)
        lib_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, lib_dock)

        settings_dock = QDockWidget("Settings", self)
        settings_dock.setObjectName("settingsDock")
        self._settings_panel.setMinimumWidth(270)
        settings_dock.setWidget(self._settings_panel)
        settings_dock.setFeatures(lib_dock.features())
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, settings_dock)

        self.resizeDocks([lib_dock, settings_dock], [220, 260], Qt.Orientation.Horizontal)
        assert self._view_menu is not None
        self._view_menu.addAction(lib_dock.toggleViewAction())
        self._view_menu.addAction(settings_dock.toggleViewAction())

    def _init_statusbar(self) -> None:
        sb = self.statusBar()
        assert sb is not None
        self._status_printer = QLabel()
        sb.addPermanentWidget(self._status_printer)

    def _init_connections(self) -> None:
        self._label_list.renderPrintPreviewSignal.connect(self._update_preview_render)
        self._label_list.renderPrintPayloadSignal.connect(self._update_print_render)
        self._label_list.contentChangedSignal.connect(self._mark_dirty)
        self._settings_panel.settings_changed_signal.connect(self._on_settings_changed)
        self._device_selector.selectedDeviceChangedSignal.connect(
            self._on_device_selected
        )
        self._library.openRequested.connect(self._open_path)
        self._library.deleteRequested.connect(self._delete_library_label)
        self._library.renameRequested.connect(self._rename_library_label)

    # ------------------------------------------------------------ preferences

    def _restore_preferences(self) -> None:
        p = self._prefs
        self._loading = True
        try:
            theme = str(p.value("ui/theme", "system"))
            self._set_theme(theme, save=False)

            raw = p.value("settings/values", "")
            values = {}
            if raw:
                try:
                    values = json.loads(str(raw))
                except ValueError:
                    LOG.warning("Ignoring corrupt saved settings")
            # Always emit once so the render context exists.
            self._settings_panel.apply_settings(values)

            self._set_zoom(float(p.value("ui/zoom", 2.0)), save=False)
            self._copies.setValue(int(p.value("ui/copies", 1)))

            geometry = p.value("window/geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
            state = p.value("window/state")
            if state is not None:
                self.restoreState(state)

            # Restore the label we were editing last time.
            session = p.value("session/elements", "")
            elements = []
            if session:
                try:
                    elements = json.loads(str(session))
                except ValueError:
                    LOG.warning("Ignoring corrupt saved session")
            if elements:
                self._label_list.set_elements(elements)
            else:
                self._label_list.populate()
                self._label_list.render_label()
            path = p.value("session/path", "")
            if path and Path(str(path)).exists():
                self._current_path = Path(str(path))
                self._doc_name = label_name_for_path(self._current_path)
            self._dirty = str(p.value("session/dirty", "false")).lower() == "true"
            self._last_label_settings = self._label_settings()
        finally:
            self._loading = False

    def _save_preferences(self) -> None:
        p = self._prefs
        p.setValue("settings/values", json.dumps(self._settings_panel.settings.to_dict()))
        p.setValue("ui/zoom", self._render.zoom)
        p.setValue("ui/copies", self._copies.value())
        p.setValue("window/geometry", self.saveGeometry())
        p.setValue("window/state", self.saveState())
        p.setValue("session/elements", json.dumps(self._label_list.get_elements()))
        p.setValue("session/path", str(self._current_path or ""))
        p.setValue("session/dirty", "true" if self._dirty else "false")
        p.sync()

    def closeEvent(self, event: QCloseEvent | None) -> None:  # noqa: N802
        # The current label is kept as the session, so nothing is lost on close.
        self._save_preferences()
        super().closeEvent(event)

    def _set_theme(self, theme: str, save: bool = True) -> None:
        if theme not in THEMES:
            theme = "system"
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme)
        self._theme_actions[theme].setChecked(True)
        if save:
            self._prefs.setValue("ui/theme", theme)

    def _set_zoom(self, zoom: float, save: bool = True) -> None:
        self._render.set_zoom(zoom)
        self.act_zoom_reset.setText(f"{round(self._render.zoom * 100)}%")
        if save:
            self._prefs.setValue("ui/zoom", self._render.zoom)

    # --------------------------------------------------------------- document

    def _label_settings(self) -> dict:
        d = self._settings_panel.settings.to_dict()
        return {k: d[k] for k in LABEL_SETTING_KEYS}

    def _mark_dirty(self) -> None:
        if self._loading:
            return
        self._dirty = True
        self._update_title()

    def _update_title(self) -> None:
        star = "•" if self._dirty else ""
        self.setWindowTitle(f"{star}{self._doc_name} — Labelle")

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            f"Save changes to “{self._doc_name}” first?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self._on_save()
        return answer == QMessageBox.StandardButton.Discard

    def _document(self) -> LabelDocument:
        return LabelDocument(
            name=self._doc_name,
            elements=self._label_list.get_elements(),
            settings=self._label_settings(),
        )

    def _load_document(self, doc: LabelDocument, path: Path | None) -> None:
        self._loading = True
        try:
            if doc.settings:
                self._settings_panel.apply_settings(doc.settings)
            self._label_list.set_elements(doc.elements)
            self._last_label_settings = self._label_settings()
        finally:
            self._loading = False
        self._current_path = path
        self._doc_name = doc.name
        self._dirty = False
        self._update_title()
        self._save_preferences()

    def _on_new(self) -> None:
        if not self._confirm_discard():
            return
        self._load_document(LabelDocument(name=UNTITLED, elements=[{"kind": "text"}]), None)
        self._status("New label")

    def _open_path(self, path: Path) -> None:
        if path == self._current_path and not self._dirty:
            return
        if not self._confirm_discard():
            return
        try:
            doc = LabelDocument.load(path)
        except (OSError, ValueError) as err:
            crash_msg_box(self, "Could not open label", err)
            return
        in_library = path.parent == library_dir()
        self._load_document(doc, path if in_library else None)
        self._status(f"Opened “{doc.name}”")

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open label", str(Path.home()),
            f"Labelle labels (*{LABEL_FILE_SUFFIX} *.json);;All files (*)",
        )
        if path:
            self._open_path(Path(path))

    def _on_save(self) -> bool:
        if self._current_path is None:
            return self._on_save_as()
        return self._write(self._current_path)

    def _on_save_as(self) -> bool:
        suggestion = "" if self._doc_name == UNTITLED else self._doc_name
        name, ok = QInputDialog.getText(
            self, "Save label", "Label name:", text=suggestion
        )
        name = name.strip()
        if not ok or not name:
            return False
        path = path_for_label_name(name)
        if path.exists() and path != self._current_path:
            answer = QMessageBox.question(
                self, "Replace label?",
                f"A saved label called “{name}” already exists. Replace it?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
        self._doc_name = name
        return self._write(path)

    def _write(self, path: Path) -> bool:
        try:
            self._document().save(path)
        except OSError as err:
            crash_msg_box(self, "Could not save label", err)
            return False
        self._current_path = path
        self._dirty = False
        self._update_title()
        self._library.refresh(select=path)
        self._save_preferences()
        self._status(f"Saved “{self._doc_name}”")
        return True

    def _on_export(self) -> None:
        default = str(Path.home() / f"{self._doc_name}{LABEL_FILE_SUFFIX}")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export label", default, f"Labelle labels (*{LABEL_FILE_SUFFIX})"
        )
        if not path:
            return
        try:
            self._document().save(Path(path))
            self._status(f"Exported to {path}")
        except OSError as err:
            crash_msg_box(self, "Could not export label", err)

    def _on_export_png(self) -> None:
        bitmap = self._render._bitmap
        if bitmap is None:
            return
        default = str(Path.home() / f"{self._doc_name}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Export image", default, "PNG (*.png)")
        if path:
            try:
                bitmap.save(path)
                self._status(f"Saved image to {path}")
            except OSError as err:
                crash_msg_box(self, "Could not save image", err)

    def _delete_library_label(self, path: Path) -> None:
        name = label_name_for_path(path)
        answer = QMessageBox.question(
            self, "Delete label?", f"Delete the saved label “{name}”?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink()
        except OSError as err:
            crash_msg_box(self, "Could not delete label", err)
            return
        if path == self._current_path:
            self._current_path = None
            self._dirty = True
            self._update_title()
        self._library.refresh()
        self._status(f"Deleted “{name}”")

    def _rename_library_label(self, path: Path) -> None:
        old = label_name_for_path(path)
        name, ok = QInputDialog.getText(self, "Rename label", "New name:", text=old)
        name = name.strip()
        if not ok or not name or name == old:
            return
        new_path = path_for_label_name(name)
        if new_path.exists():
            QMessageBox.warning(self, "Rename", f"“{name}” already exists.")
            return
        try:
            doc = LabelDocument.load(path)
            doc.name = name
            doc.save(new_path)
            path.unlink()
        except (OSError, ValueError) as err:
            crash_msg_box(self, "Could not rename label", err)
            return
        if path == self._current_path:
            self._current_path = new_path
            self._doc_name = name
            self._update_title()
        self._library.refresh(select=new_path)

    def _open_library_folder(self) -> None:
        from PyQt6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(library_dir())))

    # ----------------------------------------------------------------- labels

    def _add_element(self, kind: str) -> None:
        widget = self._label_list.add_element(kind)
        self._label_list.render_label()
        self._mark_dirty()
        if widget is not None:
            widget.setFocus()

    def _on_settings_changed(self, settings: Settings) -> None:
        self._dymo_labeler.tape_size_mm = settings.tape_size_mm
        self._dymo_labeler.lead_in_mm = settings.lead_in_mm

        self._render_context = RenderContext(
            foreground_color=settings.foreground_color,
            background_color=settings.background_color,
            height_px=self._dymo_labeler.height_px,
            preview_show_margins=settings.preview_show_margins,
        )
        self._label_list.update_params(
            dymo_labeler=self._dymo_labeler,
            h_margin_mm=settings.horizontal_margin_mm,
            min_label_width_mm=settings.min_label_width_mm,
            render_context=self._render_context,
            justify=settings.justify,
        )
        if not self._loading:
            self._prefs.setValue("settings/values", json.dumps(settings.to_dict()))
            label_settings = self._label_settings()
            if label_settings != self._last_label_settings:
                self._last_label_settings = label_settings
                self._mark_dirty()
        self._update_print_state()

    def _update_preview_render(self, preview_bitmap: Image.Image) -> None:
        self._render.update_preview_render(preview_bitmap)

    def _update_print_render(self, label_bitmap_to_print: Image.Image) -> None:
        self._label_bitmap_to_print = label_bitmap_to_print
        lead_in = self._dymo_labeler.lead_in_mm
        length_mm = label_bitmap_to_print.width / PIXELS_PER_MM + lead_in
        self._length_label.setText(f"≈ {length_mm:.0f} mm long")

    def _update_print_state(self) -> None:
        ready = self._dymo_labeler.is_ready
        self._print_button.setEnabled(ready)
        self.act_print.setEnabled(ready)
        if ready:
            device = self._dymo_labeler.device
            product = device.product if device is not None else "printer"
            self._status_printer.setText(f"●  {product} connected")
            self._printer_hint.setText(
                f"{self._dymo_labeler.tape_size_mm} mm tape"
            )
        else:
            self._status_printer.setText("○  No printer connected")
            self._printer_hint.setText("Connect a printer to print")

    def _on_print_label(self) -> None:
        if not self._dymo_labeler.is_ready:
            return
        try:
            if self._label_bitmap_to_print is None:
                raise RuntimeError("No label to print!")
            copies = self._copies.value()
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                for i in range(copies):
                    self._status(f"Printing {i + 1} of {copies}…")
                    QApplication.processEvents()
                    self._dymo_labeler.print(self._label_bitmap_to_print)
            finally:
                QApplication.restoreOverrideCursor()
            self._status(f"Printed {copies} label{'s' if copies > 1 else ''}")
        except (DymoLabelerPrintError, RuntimeError) as err:
            self._status("Printing failed")
            crash_msg_box(self, "Printing Failed!", err)

    def _on_device_selected(self) -> None:
        self._dymo_labeler.device = self._device_selector.selected_device
        self._update_print_state()

    def _status(self, message: str) -> None:
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(message, 5000)

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About Labelle",
            f"<h3>Labelle {__version__}</h3>"
            "<p>Label designer for DYMO label makers.</p>"
            f"<p>Saved labels: <code>{library_dir()}</code><br>"
            f"Preferences: <code>{self._prefs.fileName()}</code></p>",
        )


def parse(app) -> None:
    """Parse the arguments and options of the given app object."""
    parser = QCommandLineParser()
    parser.addHelpOption()

    verbose_option = QCommandLineOption(["v", "verbose"], "Verbose output.")
    parser.addOption(verbose_option)
    parser.process(app)

    is_verbose = parser.isSet(verbose_option)
    if (not is_verbose) and (not is_verbose_env_vars()):
        # Neither the --verbose flag nor the environment variable is set.
        set_not_verbose()


def main() -> None:
    configure_logging()
    with system_run():
        app = QApplication(sys.argv)
        app.setApplicationName("Labelle")
        app.setDesktopFileName("labelle-gui")
        parse(app)
        window = LabelleWindow()
        window.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
