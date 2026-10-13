import base64

import pytest
from fakes import FakeRunner

from dpi_dashboard.backends import WindowsServiceBackend

QUERY_RUNNING = """
SERVICE_NAME: zapret
        TYPE               : 10  WIN32_OWN_PROCESS
        STATE              : 4  RUNNING
"""
QUERY_STOPPED = QUERY_RUNNING.replace("4  RUNNING", "1  STOPPED")
QC_AUTO = """
SERVICE_NAME: zapret
        TYPE               : 10  WIN32_OWN_PROCESS
        START_TYPE         : 2   AUTO_START
"""
QC_DEMAND = QC_AUTO.replace("2   AUTO_START", "3   DEMAND_START")
MISSING = "[SC] OpenService FAILED 1060:\n\nThe specified service does not exist."


def make(query, qc, query_code=0):
    return WindowsServiceBackend("zapret", FakeRunner({
        ("sc", "query"): (query_code, query), ("sc", "qc"): (0, qc)}))


def test_running_auto():
    s = make(QUERY_RUNNING, QC_AUTO).state()
    assert (s.installed, s.active, s.enabled) == (True, True, True)


def test_stopped_manual():
    s = make(QUERY_STOPPED, QC_DEMAND).state()
    assert (s.installed, s.active, s.enabled) == (True, False, False)


def test_missing_service():
    assert make(MISSING, "", query_code=1060).state().installed is False


def test_localized_labels_still_parse():
    # Only the numbers matter; the words next to them may be translated.
    q = QUERY_RUNNING.replace("RUNNING", "CALISIYOR")
    assert make(q, QC_AUTO).state().active


@pytest.mark.parametrize("name", ["a b", "x;rm", "zap'ret", "", "a$b"])
def test_rejects_unsafe_names(name):
    with pytest.raises(ValueError):
        WindowsServiceBackend(name, FakeRunner({}))


def test_elevated_command_is_encoded():
    b = WindowsServiceBackend("GoodbyeDPI", FakeRunner({}))
    cmd = b.toggle_command(True)
    assert cmd[:2] == ["powershell", "-NoProfile"]
    encoded = cmd[-1].split("'-EncodedCommand','")[1].split("'")[0]
    script = base64.b64decode(encoded).decode("utf-16-le")
    assert "Start-Service -Name 'GoodbyeDPI'" in script
    assert "-StartupType Automatic" in script
    off = base64.b64decode(b.toggle_command(False)[-1].split("'-EncodedCommand','")[1]
                           .split("'")[0]).decode("utf-16-le")
    assert "Stop-Service" in off and "-StartupType Manual" in off


def test_uac_cancel_is_reported():
    b = WindowsServiceBackend("zapret", FakeRunner({("powershell",): (1223, "")}))
    res = b.set_enabled(True)
    assert not res.ok and res.cancelled
