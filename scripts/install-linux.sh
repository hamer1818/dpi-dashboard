#!/usr/bin/env bash
# Installs DPI Dashboard for the current user. No root needed.
#
#   ./scripts/install-linux.sh            install or update
#   ./scripts/uninstall-linux.sh          remove
#
# Uses a private virtual environment. If PyQt6 is already installed system-wide
# (python-pyqt6 / python3-pyqt6), it is reused instead of downloading ~100 MB.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/dpi-dashboard"
BIN="$HOME/.local/bin"

# Run a cache-refresh tool if this desktop has it; never fail because of it.
run_if_present() {
    if command -v "$1" >/dev/null 2>&1; then "$@" >/dev/null 2>&1 || true; fi
}

say()  { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m! %s\033[0m\n' "$*" >&2; }

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
    || { echo "Python 3.10 or newer is required" >&2; exit 1; }
python3 -c 'import venv, ensurepip' 2>/dev/null \
    || { echo "The Python venv module is missing (Debian/Ubuntu: sudo apt install python3-venv)" >&2; exit 1; }

say "Creating environment in $APP/venv"
python3 -m venv --clear --system-site-packages "$APP/venv"
if "$APP/venv/bin/python" -c 'import PyQt6.QtWidgets' 2>/dev/null; then
    say "Using the system PyQt6"
    "$APP/venv/bin/pip" install --quiet --no-deps "$SRC"
else
    say "Installing PyQt6 from PyPI"
    "$APP/venv/bin/pip" install --quiet "$SRC"
fi

mkdir -p "$BIN" "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
ln -sf "$APP/venv/bin/dpi-dashboard" "$BIN/dpi-dashboard"
install -m 0644 "$SRC/src/dpi_dashboard/assets/icon.svg" \
    "$DATA/icons/hicolor/scalable/apps/dpi-dashboard.svg"
# Absolute path: desktop sessions do not always have ~/.local/bin in PATH.
sed "s|^Exec=.*|Exec=$APP/venv/bin/dpi-dashboard|" "$SRC/packaging/linux/dpi-dashboard.desktop" \
    > "$DATA/applications/dpi-dashboard.desktop"

run_if_present update-desktop-database -q "$DATA/applications"
run_if_present gtk-update-icon-cache -q -t "$DATA/icons/hicolor"
run_if_present kbuildsycoca6
run_if_present kbuildsycoca5

say "Installed: search for \"DPI Dashboard\" in your application menu."

# Things the app needs at run time but does not install itself.
[ -d /run/systemd/system ] || warn "systemd is not running; only systemd services are supported on Linux."
command -v pkexec >/dev/null || warn "pkexec (polkit) not found; turning the service on/off will not work."
if command -v systemctl >/dev/null && ! systemctl cat zapret.service >/dev/null 2>&1; then
    warn "zapret.service was not found. Install zapret first: https://github.com/bol-van/zapret"
fi
