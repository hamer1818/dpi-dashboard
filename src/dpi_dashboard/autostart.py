"""Start DPI Dashboard when the user logs in, in the system tray (--minimized).

- Windows: a value in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
- Linux: an XDG autostart entry, ~/.config/autostart/dpi-dashboard.desktop.

Only the current user's login is affected; no administrator rights are needed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "DPI Dashboard"
MINIMIZED = "--minimized"


def launch_command() -> list[str]:
    """How to start this program again (after an update, or at login)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    script = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if script and script.stem == "dpi-dashboard" and script.exists():
        return [str(script.resolve())]
    python = Path(sys.executable)
    if sys.platform == "win32" and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")      # no console window
    return [str(python), "-m", "dpi_dashboard"]


def desktop_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "dpi-dashboard.desktop"


def _desktop_exec(args: list[str]) -> str:
    """Exec= line: arguments with special characters go in double quotes (XDG spec)."""
    def q(a: str) -> str:
        if re.fullmatch(r"[A-Za-z0-9_./=:+-]+", a):
            return a
        return '"' + re.sub(r'(["`$\\])', r"\\\1", a) + '"'
    return " ".join(q(a) for a in args).replace("%", "%%")


def _windows_command() -> str:
    return subprocess.list2cmdline([*launch_command(), MINIMIZED])


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, RUN_VALUE)
            return True
        except OSError:
            return False
    return desktop_file().exists()


def set_enabled(on: bool) -> None:
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, _windows_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return
    f = desktop_file()
    if not on:
        f.unlink(missing_ok=True)
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("[Desktop Entry]\n"
                 "Type=Application\n"
                 "Name=DPI Dashboard\n"
                 f"Exec={_desktop_exec([*launch_command(), MINIMIZED])}\n"
                 "Icon=dpi-dashboard\n"
                 "Terminal=false\n"
                 "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")


def refresh() -> None:
    """Point an existing entry at the current program (it may have been moved)."""
    try:
        if is_enabled():
            set_enabled(True)
    except OSError:
        pass
