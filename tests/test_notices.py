"""THIRD_PARTY_NOTICES.md must list the versions that are actually bundled."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def locked():
    text = (ROOT / "packaging/requirements/release-windows.txt").read_text()
    return dict(re.findall(r"^([a-z0-9-]+)==(\S+)", text, re.M))


def test_bundled_versions_match_the_lock_file():
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text()
    lock = locked()
    for name, label in [("pyqt6", "PyQt6 (Riverbank Computing)"), ("pyqt6-qt6", "Qt 6"),
                        ("pyqt6-sip", "PyQt6-sip"), ("pyinstaller", "PyInstaller bootloader")]:
        row = next(line for line in notices.splitlines() if line.startswith(f"| {label}"))
        assert f"| {lock[name]} |" in row, f"{label}: notices say {row!r}, lock has {lock[name]}"


def test_license_texts_are_present():
    for f in ["GPL-3.0.txt", "LGPL-3.0.txt", "Python-PSF-2.0.txt", "PyQt6-sip-BSD-2-Clause.txt"]:
        assert (ROOT / "licenses" / f).stat().st_size > 500
