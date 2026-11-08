#!/usr/bin/env python3
"""Install (or remove) the Labelle GUI launcher + icon for the current user.

Creates:
  ~/.local/share/applications/labelle-gui.desktop
  ~/.local/share/icons/hicolor/<N>x<N>/apps/labelle-gui.png

The .desktop file name must match the app id set in labelle.gui.gui
(QApplication.setDesktopFileName("labelle-gui")) so GNOME groups the running
window with this launcher and "Pin to Dash" works.

Usage: python3 install_desktop.py [--uninstall]   (needs Pillow for icons)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ID = "labelle-gui"
REPO = Path(__file__).resolve().parent.parent
LOGO = REPO / "labelle.png"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
APPS_DIR = DATA_HOME / "applications"
ICON_ROOT = DATA_HOME / "icons" / "hicolor"


def find_executable() -> str:
    found = shutil.which(APP_ID)
    if found:
        return found
    candidate = Path.home() / ".local" / "bin" / APP_ID
    if candidate.exists():
        return str(candidate)
    sys.exit(f"Could not find {APP_ID}; install labelle first.")


def install_icons() -> None:
    from PIL import Image

    logo = Image.open(LOGO).convert("RGBA")
    # Trim transparent border so the dragonfly fills the icon
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    side = max(logo.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    for size in SIZES:
        out = ICON_ROOT / f"{size}x{size}" / "apps" / f"{APP_ID}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        # ~6% padding, like most app icons
        inner = round(size * 0.94)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        icon = square.resize((inner, inner), Image.Resampling.LANCZOS)
        offset = (size - inner) // 2
        canvas.paste(icon, (offset, offset), icon)
        canvas.save(out)


def install_desktop_file(exe: str) -> Path:
    APPS_DIR.mkdir(parents=True, exist_ok=True)
    path = APPS_DIR / f"{APP_ID}.desktop"
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Labelle\n"
        "GenericName=Label Printer\n"
        "Comment=Design and print labels on DYMO label makers\n"
        f'Exec="{exe}" %F\n'
        f"TryExec={exe}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Office;\n"
        "Keywords=label;dymo;printer;tape;labelmanager;\n"
        f"StartupWMClass={APP_ID}\n"
        "StartupNotify=true\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def refresh_caches() -> None:
    for cmd in (
        ["update-desktop-database", str(APPS_DIR)],
        ["gtk-update-icon-cache", "-q", "-t", "-f", str(ICON_ROOT)],
    ):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=False, capture_output=True)


def uninstall() -> None:
    (APPS_DIR / f"{APP_ID}.desktop").unlink(missing_ok=True)
    for size in SIZES:
        (ICON_ROOT / f"{size}x{size}" / "apps" / f"{APP_ID}.png").unlink(missing_ok=True)
    refresh_caches()
    print("Removed Labelle launcher and icons.")


def main() -> None:
    if "--uninstall" in sys.argv:
        uninstall()
        return
    exe = find_executable()
    install_icons()
    desktop = install_desktop_file(exe)
    refresh_caches()
    print(f"Installed launcher: {desktop}")
    print(f"Icons: {ICON_ROOT}/*/apps/{APP_ID}.png")


if __name__ == "__main__":
    main()
