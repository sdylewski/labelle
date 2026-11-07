import logging

from PIL import Image, ImageQt
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

LOG = logging.getLogger(__name__)


class QRender(QLabel):
    """Shows the label preview, scaled by an adjustable zoom factor."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bitmap: Image.Image | None = None
        self._zoom = 2.0
        self._init_elements()

    def _init_elements(self) -> None:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.5, min(8.0, zoom))
        self._refresh()

    def update_preview_render(self, preview_bitmap: Image.Image) -> None:
        self._bitmap = preview_bitmap
        self._refresh()

    def _refresh(self) -> None:
        if self._bitmap is None:
            return
        pixmap = QPixmap.fromImage(ImageQt.ImageQt(self._bitmap))
        if self._zoom != 1.0:
            pixmap = pixmap.scaled(
                round(pixmap.width() * self._zoom),
                round(pixmap.height() * self._zoom),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
                if self._zoom < 1
                else Qt.TransformationMode.FastTransformation,
            )
        self.setPixmap(pixmap)
        self.adjustSize()
