from fakes import FakeRunner

from dpi_dashboard.backends import SystemdBackend

SHOW = ("systemctl", "show", "zapret.service")


def backend(code, out, toggle_code=0):
    r = FakeRunner({SHOW: (code, out), ("pkexec",): (toggle_code, "")})
    return SystemdBackend("zapret.service", r), r


def test_active_and_enabled():
    b, _ = backend(0, "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n")
    s = b.state()
    assert (s.installed, s.active, s.enabled) == (True, True, True)


def test_inactive_and_disabled():
    b, _ = backend(0, "LoadState=loaded\nActiveState=inactive\nUnitFileState=disabled\n")
    s = b.state()
    assert (s.installed, s.active, s.enabled) == (True, False, False)


def test_not_found():
    b, _ = backend(0, "LoadState=not-found\nActiveState=inactive\nUnitFileState=\n")
    assert b.state().installed is False


def test_toggle_command():
    b, _ = backend(0, "")
    cmd = b.toggle_command(True)
    assert cmd[0] == "pkexec" and cmd[1].endswith("systemctl")
    assert cmd[2:] == ["enable", "--now", "zapret.service"]
    assert b.toggle_command(False)[2] == "disable"


def test_set_enabled_results(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    assert SystemdBackend("zapret.service", FakeRunner({("pkexec",): (0, "")})) \
        .set_enabled(True).ok
    res = SystemdBackend("zapret.service", FakeRunner({("pkexec",): (126, "")})).set_enabled(True)
    assert not res.ok and res.cancelled


def test_missing_pkexec(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    res = SystemdBackend("zapret.service", FakeRunner({})).set_enabled(True)
    assert not res.ok and "pkexec" in res.message
