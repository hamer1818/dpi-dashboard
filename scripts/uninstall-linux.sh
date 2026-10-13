#!/usr/bin/env bash
# Removes what install-linux.sh installed. Leaves your settings and zapret alone.
set -euo pipefail
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$DATA/dpi-dashboard"
rm -f "$HOME/.local/bin/dpi-dashboard" \
      "$DATA/applications/dpi-dashboard.desktop" \
      "$DATA/icons/hicolor/scalable/apps/dpi-dashboard.svg"
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
echo "DPI Dashboard removed. Settings remain in ${XDG_CONFIG_HOME:-$HOME/.config}/dpi-dashboard/"
