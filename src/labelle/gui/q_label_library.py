"""Side panel listing saved labels."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from labelle.gui.label_store import label_name_for_path, library_dir, list_library

LOG = logging.getLogger(__name__)


class QLabelLibrary(QWidget):
    openRequested = QtCore.pyqtSignal(Path, name="openRequested")
    deleteRequested = QtCore.pyqtSignal(Path, name="deleteRequested")
    renameRequested = QtCore.pyqtSignal(Path, name="renameRequested")

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Search saved labels…")
        self._filter.setClearButtonEnabled(True)
        self._list = QListWidget()
        self._list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._open_button = QPushButton("Open")
        self._delete_button = QPushButton("Delete")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._filter)
        layout.addWidget(self._list, 1)
        buttons = QHBoxLayout()
        buttons.addWidget(self._open_button)
        buttons.addWidget(self._delete_button)
        layout.addLayout(buttons)

        self._filter.textChanged.connect(self._apply_filter)
        self._list.itemActivated.connect(self._on_activated)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.currentItemChanged.connect(self._update_buttons)
        self._open_button.clicked.connect(self._open_current)
        self._delete_button.clicked.connect(self._delete_current)

        self.refresh()

    def refresh(self, select: Path | None = None) -> None:
        self._list.clear()
        for path in list_library():
            item = QListWidgetItem(label_name_for_path(path))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            item.setToolTip(str(path))
            self._list.addItem(item)
            if select is not None and path == select:
                self._list.setCurrentItem(item)
        self._apply_filter(self._filter.text())
        self._update_buttons()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._list.count()):
            item = self._list.item(i)
            assert item is not None
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _current_path(self) -> Path | None:
        item = self._list.currentItem()
        if item is None or item.isHidden():
            return None
        return item.data(QtCore.Qt.ItemDataRole.UserRole)

    def _update_buttons(self, *_args) -> None:
        has = self._current_path() is not None
        self._open_button.setEnabled(has)
        self._delete_button.setEnabled(has)

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.openRequested.emit(item.data(QtCore.Qt.ItemDataRole.UserRole))

    def _open_current(self) -> None:
        path = self._current_path()
        if path is not None:
            self.openRequested.emit(path)

    def _delete_current(self) -> None:
        path = self._current_path()
        if path is not None:
            self.deleteRequested.emit(path)

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        menu = QMenu(self)
        open_action = rename_action = delete_action = None
        if item is not None:
            open_action = menu.addAction("Open")
            rename_action = menu.addAction("Rename…")
            delete_action = menu.addAction("Delete")
            menu.addSeparator()
        folder_action = menu.addAction("Show labels folder")
        refresh_action = menu.addAction("Refresh")
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen is None:
            return
        path = item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None
        if chosen == open_action and path:
            self.openRequested.emit(path)
        elif chosen == rename_action and path:
            self.renameRequested.emit(path)
        elif chosen == delete_action and path:
            self.deleteRequested.emit(path)
        elif chosen == folder_action:
            QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(library_dir())))
        elif chosen == refresh_action:
            self.refresh()
