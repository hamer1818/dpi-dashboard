import sys

import pytest

from dpi_dashboard import autostart

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="XDG autostart")


def test_linux_entry_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(autostart, "launch_command", lambda: ["/opt/my apps/dpi-dashboard"])
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    text = autostart.desktop_file().read_text()
    assert autostart.is_enabled()
    assert 'Exec="/opt/my apps/dpi-dashboard" --minimized\n' in text
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    autostart.set_enabled(False)                         # already off: no error


def test_launch_command_from_source(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["-m"])
    assert autostart.launch_command()[1:] == ["-m", "dpi_dashboard"]
