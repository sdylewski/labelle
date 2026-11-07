#!/usr/bin/env bash
# Reinstall labelle / labelle-gui from this local checkout using pipx.
#
# Works when run as your normal user or via sudo/root: pipx installs are
# per-user, so when run as root it installs for $SUDO_USER (or $LABELLE_USER),
# replacing the existing ~/.local/bin/labelle and labelle-gui.
#
# Usage:  sudo ./scripts/install-local.sh      (or just ./scripts/install-local.sh)
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_USER="${LABELLE_USER:-${SUDO_USER:-$(id -un)}}"

if [[ "$TARGET_USER" == "root" ]]; then
    echo "Refusing to install into root's pipx. Run via sudo from your account," >&2
    echo "or set LABELLE_USER=<your username>." >&2
    exit 1
fi

run_as_user() {
    if [[ "$(id -un)" == "$TARGET_USER" ]]; then
        "$@"
    else
        sudo -u "$TARGET_USER" -H env "PATH=/home/$TARGET_USER/.local/bin:/usr/local/bin:/usr/bin:/bin" "$@"
    fi
}

echo "Installing labelle from $SRC_DIR for user $TARGET_USER ..."
run_as_user pipx install --force "$SRC_DIR"

echo
run_as_user labelle --version || true
echo "Done. Start the GUI with: labelle-gui"
echo "To go back to the stock release: pipx install --force labelle"
