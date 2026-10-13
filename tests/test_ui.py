import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from dpi_dashboard.app import Dashboard  # noqa: E402
from dpi_dashboard.backends import Backend, ServiceState, ToggleResult  # noqa: E402
from dpi_dashboard.config import Config  # noqa: E402
from dpi_dashboard.i18n import Translator  # noqa: E402
from dpi_dashboard.probe import Attempt, HostResult  # noqa: E402


class FakeBackend(Backend):
    kind = "fake"

    def __init__(self, st):
        super().__init__("zapret.service", runner=None)
        self.st = st

    def state(self):
        return self.st

    def set_enabled(self, on):
        return ToggleResult(True)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def window(st, **kw):
    return Dashboard(FakeBackend(st) if st else None, Config(hosts=["a.com", "b.com"]),
                     Translator("en"), **kw)


def test_on_state(app):
    w = window(ServiceState(True, True, True))
    assert w.state_label.text() == "ON"
    assert w.toggle_btn.text() == "Turn off" and w.toggle_btn.isEnabled()
    assert "starts at boot" in w.detail.text()


def test_off_state(app):
    w = window(ServiceState(True, False, False))
    assert w.state_label.text() == "OFF" and w.toggle_btn.text() == "Turn on"


def test_missing_service(app):
    w = window(ServiceState(False))
    assert w.state_label.text() == "NOT FOUND" and not w.toggle_btn.isEnabled()
    assert "zapret.service" in w.msg.text()


def test_no_backend(app):
    w = window(None)
    assert not w.toggle_btn.isEnabled() and "service manager" in w.msg.text()


def test_results_and_cancel(app):
    w = window(ServiceState(True, False, False))
    w.test_btn.setEnabled(False)
    w.show_results([HostResult("a.com", [Attempt(True)] * 3),
                    HostResult("b.com", [Attempt(False, "reset")] * 3)])
    assert w.result_labels["a.com"].text() == "3/3"
    assert w.result_labels["b.com"].text() == "0/3"
    assert "DPI" in w.result_labels["b.com"].toolTip()
    assert "blocked" in w.msg.text()
    w.on_toggled((True, ToggleResult(False, cancelled=True)))
    assert "Cancelled" in w.msg.text() and not w.busy


def test_config_warning_is_shown(app):
    w = window(ServiceState(True, True, True), warning="config.json: ignored tries")
    assert "ignored tries" in w.msg.text()
