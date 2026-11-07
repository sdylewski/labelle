"""Saving/loading label designs and GUI preferences."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSettings, QStandardPaths

LOG = logging.getLogger(__name__)

LABEL_FILE_FORMAT = "labelle-gui-label"
LABEL_FILE_VERSION = 1
LABEL_FILE_SUFFIX = ".label.json"

# Settings that describe the label itself (saved with each label). Printer-specific
# preferences such as lead-in are deliberately not part of a label file.
LABEL_SETTING_KEYS = (
    "tape_size_mm",
    "foreground_color",
    "background_color",
    "horizontal_margin_mm",
    "min_label_width_mm",
    "justify",
)


@dataclass
class LabelDocument:
    name: str
    elements: list[dict[str, Any]]
    settings: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "format": LABEL_FILE_FORMAT,
                "version": LABEL_FILE_VERSION,
                "name": self.name,
                "settings": {
                    k: v for k, v in self.settings.items() if k in LABEL_SETTING_KEYS
                },
                "elements": self.elements,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str, fallback_name: str = "Untitled") -> LabelDocument:
        data = json.loads(text)
        if not isinstance(data, dict) or data.get("format") != LABEL_FILE_FORMAT:
            raise ValueError("Not a labelle-gui label file")
        elements = data.get("elements", [])
        if not isinstance(elements, list):
            raise ValueError("Invalid label file: 'elements' must be a list")
        settings = data.get("settings", {})
        return cls(
            name=str(data.get("name") or fallback_name),
            elements=[e for e in elements if isinstance(e, dict)],
            settings=settings if isinstance(settings, dict) else {},
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> LabelDocument:
        return cls.from_json(
            path.read_text(encoding="utf-8"), fallback_name=label_name_for_path(path)
        )


def library_dir() -> Path:
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )
    path = Path(base) / "labelle" / "labels"
    path.mkdir(parents=True, exist_ok=True)
    return path


def label_name_for_path(path: Path) -> str:
    name = path.name
    if name.endswith(LABEL_FILE_SUFFIX):
        return name[: -len(LABEL_FILE_SUFFIX)]
    return path.stem


def path_for_label_name(name: str) -> Path:
    safe = re.sub(r"[^\w\-. ]+", "_", name).strip(" .") or "label"
    return library_dir() / f"{safe}{LABEL_FILE_SUFFIX}"


def list_library() -> list[Path]:
    return sorted(
        library_dir().glob(f"*{LABEL_FILE_SUFFIX}"),
        key=lambda p: label_name_for_path(p).lower(),
    )


def preferences() -> QSettings:
    """Preferences stored in ~/.config/labelle/labelle-gui.conf."""
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "labelle",
        "labelle-gui",
    )
