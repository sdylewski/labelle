from __future__ import annotations

import logging
from typing import Any

from PIL import Image
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem, QMenu

from labelle.gui.common import crash_msg_box
from labelle.gui.q_label_widgets import (
    LABEL_WIDGET_CLASSES,
    BaseLabelWidget,
    EmptyRenderEngine,
)
from labelle.lib.constants import Direction
from labelle.lib.devices.dymo_labeler import DymoLabeler
from labelle.lib.render_engines import (
    HorizontallyCombinedRenderEngine,
    PrintPayloadRenderEngine,
    PrintPreviewRenderEngine,
    RenderContext,
)
from labelle.lib.render_engines.render_engine import (
    RenderEngine,
    RenderEngineException,
)
from labelle.lib.utils import mm_to_px

LOG = logging.getLogger(__name__)


class QLabelList(QListWidget):
    """A custom QListWidget for displaying and managing Dymo label widgets.

    Args:
    ----
        render_context (RenderContext): The render context to use for rendering the
        label.
        parent (QWidget): The parent widget of this QListWidget.

    Attributes:
    ----------
        renderPrintPreviewSignal (QtCore.pyqtSignal): A signal emitted when the preview
            is rendered.
        renderPrintPayloadSignal (QtCore.pyqtSignal): A signal emitted when the print
            payload is rendered.
        render_context (RenderContext): The render context used for rendering the label.

    Methods:
    -------
        __init__(self, render_context, parent=None): Initializes the QListWidget
            with the given render context and parent.
        dropEvent(self, e) -> None: Overrides the default drop event to update
            the label rendering.
        update_render_engine(self, render_engine): Updates the render context used
            for rendering the label.
        render_preview(self): Renders the payload using the current render context and
            emits the renderPrintPreviewSignal.
        render_print(self): Renders the print payload using the current render context
            and emits the renderPrintPayloadSignal.
        render_label(self): Renders the both preview and print payloads using the
            current render context and emits the corresponding signals.
        contextMenuEvent(self, event): Overrides the default context menu event to
            add or delete label widgets.

    """

    renderPrintPreviewSignal = QtCore.pyqtSignal(
        Image.Image, name="renderPrintPreviewSignal"
    )
    renderPrintPayloadSignal = QtCore.pyqtSignal(
        Image.Image, name="renderPrintPayloadSignal"
    )
    # Emitted whenever the user edits, adds, removes or reorders elements
    contentChangedSignal = QtCore.pyqtSignal(name="contentChangedSignal")
    render_context: RenderContext | None
    dymo_labeler: DymoLabeler | None
    h_margin_mm: float
    min_label_width_mm: float | None
    justify: Direction

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dymo_labeler = None
        self.h_margin_mm = 0.0
        self.min_label_width_mm = None
        self.justify = Direction.CENTER
        self.render_context = None
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def populate(self) -> None:
        self.add_element("text")

    def add_element(
        self, kind: str, state: dict[str, Any] | None = None
    ) -> BaseLabelWidget | None:
        """Append a new element of the given kind ("text", "qr", ...)."""
        assert self.render_context is not None
        widget_cls = LABEL_WIDGET_CLASSES.get(kind)
        if widget_cls is None:
            LOG.warning(f"Unknown label element kind {kind!r}, skipping")
            return None
        item_widget = widget_cls(self.render_context)
        if state:
            item_widget.set_state(state)
        item = QListWidgetItem(self)
        item.setSizeHint(item_widget.sizeHint())
        self.addItem(item)
        self.setItemWidget(item, item_widget)
        item_widget.itemRenderSignal.connect(self._on_item_changed)
        self.setCurrentItem(item)
        return item_widget

    def _on_item_changed(self) -> None:
        self.render_label()
        self.contentChangedSignal.emit()

    def remove_selected(self) -> None:
        row = self.currentRow()
        if row >= 0:
            self.takeItem(row)
            self.render_label()
            self.contentChangedSignal.emit()

    def get_elements(self) -> list[dict[str, Any]]:
        """Return all elements, in order, as JSON-serializable dicts."""
        elements = []
        for i in range(self.count()):
            item_widget = self.itemWidget(self.item(i))
            if isinstance(item_widget, BaseLabelWidget):
                elements.append({"kind": item_widget.kind, **item_widget.get_state()})
        return elements

    def set_elements(self, elements: list[dict[str, Any]]) -> None:
        """Replace all elements with the given ones."""
        self.blockSignals(True)
        try:
            self.clear()
            for element in elements:
                state = dict(element)
                kind = state.pop("kind", "text")
                self.add_element(kind, state)
        finally:
            self.blockSignals(False)
        self.render_label()

    def keyPressEvent(self, e) -> None:
        if e.key() == QtCore.Qt.Key.Key_Delete and not isinstance(
            self.focusWidget(), (QtWidgets.QLineEdit, QtWidgets.QPlainTextEdit)
        ):
            self.remove_selected()
            return
        super().keyPressEvent(e)

    def dropEvent(self, e) -> None:
        """Override the default drop event to update the label rendering.

        Args:
        ----
            e (QDropEvent): The drop event.

        """
        super().dropEvent(e)
        self.render_label()
        self.contentChangedSignal.emit()

    def update_params(
        self,
        dymo_labeler: DymoLabeler,
        h_margin_mm: float,
        min_label_width_mm: float,
        render_context: RenderContext,
        justify: Direction = Direction.CENTER,
    ):
        """Update the render context used for rendering the label.

        Args:
        ----
            dymo_labeler: an instance of DymoLabeler object
            h_margin_mm: horizontal margin [mm]
            min_label_width_mm: minimum label width [mm]
            render_context (RenderContext): The new render context to use.
            justify: justification [left,center, right]

        """
        self.dymo_labeler = dymo_labeler
        self.h_margin_mm = h_margin_mm
        self.min_label_width_mm = min_label_width_mm
        self.justify = justify
        self.render_context = render_context
        for i in range(self.count()):
            item_widget = self.itemWidget(self.item(i))
            assert isinstance(item_widget, BaseLabelWidget)
            item_widget.render_context = render_context
        self.render_label()

    @property
    def _payload_render_engine(self):
        render_engines: list[RenderEngine] = []
        for i in range(self.count()):
            item = self.item(i)
            item_widget = self.itemWidget(self.item(i))
            if item_widget and item:
                item.setSizeHint(item_widget.sizeHint())
                assert isinstance(item_widget, BaseLabelWidget)
                render_engine = item_widget.render_engine
                if render_engine is not None:
                    render_engines.append(render_engine)
        return HorizontallyCombinedRenderEngine(render_engines=render_engines)

    def render_preview(self) -> None:
        assert self.dymo_labeler is not None
        assert self.render_context is not None
        render_engine = PrintPreviewRenderEngine(
            render_engine=self._payload_render_engine,
            justify=self.justify,
            visible_horizontal_margin_px=mm_to_px(self.h_margin_mm),
            labeler_margin_px=self.dymo_labeler.labeler_margin_px,
            max_width_px=None,
            min_width_px=mm_to_px(self.min_label_width_mm),
        )
        try:
            bitmap = render_engine.render(self.render_context)
        except RenderEngineException as err:
            crash_msg_box(self, "Render Engine Failed!", err)
            bitmap = EmptyRenderEngine().render(self.render_context)

        self.renderPrintPreviewSignal.emit(bitmap)

    def render_print(self) -> None:
        assert self.dymo_labeler is not None
        assert self.render_context is not None
        render_engine = PrintPayloadRenderEngine(
            render_engine=self._payload_render_engine,
            justify=self.justify,
            visible_horizontal_margin_px=mm_to_px(self.h_margin_mm),
            labeler_margin_px=self.dymo_labeler.labeler_margin_px,
            max_width_px=None,
            min_width_px=mm_to_px(self.min_label_width_mm),
        )
        try:
            bitmap, _ = render_engine.render_with_meta(self.render_context)
        except RenderEngineException as err:
            crash_msg_box(self, "Render Engine Failed!", err)
            bitmap = EmptyRenderEngine().render(self.render_context)

        self.renderPrintPayloadSignal.emit(bitmap)

    def render_label(self) -> None:
        self.render_preview()
        self.render_print()

    def contextMenuEvent(self, event) -> None:
        """Override the default context menu event to add or delete label widgets.

        Args:
        ----
            event (QContextMenuEvent): The context menu event.

        """
        assert self.render_context is not None
        contextMenu = QMenu(self)
        add_text: QAction | None = contextMenu.addAction("Add Text")
        add_qr: QAction | None = contextMenu.addAction("Add QR")
        add_barcode: QAction | None = contextMenu.addAction("Add Barcode")
        add_img: QAction | None = contextMenu.addAction("Add Image")
        delete: QAction | None = contextMenu.addAction("Delete")
        menu_click = contextMenu.exec(event.globalPos())

        kinds = {add_text: "text", add_qr: "qr", add_barcode: "barcode", add_img: "image"}
        if menu_click in kinds:
            self.add_element(kinds[menu_click])
            self.contentChangedSignal.emit()
        elif menu_click == delete:
            item_to_delete = self.itemAt(event.pos())
            if item_to_delete is not None:
                self.takeItem(self.row(item_to_delete))
                self.contentChangedSignal.emit()
        self.render_label()
