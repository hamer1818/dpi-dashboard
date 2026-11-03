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


def test_about_shows_licenses_and_warranty(app):
    from dpi_dashboard import __version__
    w = window(ServiceState(True, True, True))
    text = w.about_text()
    for part in ("MIT", "GPL", "LGPL", "NO WARRANTY", __version__, "THIRD_PARTY_NOTICES.md"):
        assert part in text
    assert "About and licenses" in w.about.text()


def test_close_goes_to_tray_or_quits(app, monkeypatch):
    from dpi_dashboard import app as app_mod
    quits = []
    monkeypatch.setattr(app_mod.QApplication.instance(), "quit", lambda: quits.append(1))
    w = window(ServiceState(True, True, True))
    w.tray = type("T", (), {"showMessage": lambda *a: None})()      # a tray without a screen
    w.show()
    w.close()
    assert not w.isVisible() and not quits                        # hidden, still running
    w.cfg.close_to_tray = False
    w.show()
    w.close()
    assert quits


def test_settings_menu_saves_options(app, monkeypatch):
    saved = {}
    monkeypatch.setattr("dpi_dashboard.config.set_value", lambda k, v: saved.update({k: v}))
    w = window(ServiceState(True, True, True))
    w.update_action.setChecked(False)
    w.tray_action.setChecked(False)
    assert saved == {"auto_update": False, "close_to_tray": False}
    assert not w.cfg.auto_update and not w.cfg.close_to_tray


def test_update_ready_and_available(app):
    from dpi_dashboard.updater import Release
    w = window(ServiceState(True, True, True))
    rel = Release("v9.0.0", "9.0.0", "https://example.com/r", None, None)
    w.on_update_checked(("available", rel, None), manual=False)
    assert "9.0.0" in w.update_label.text() and "example.com/r" in w.update_label.text()
    w.on_update_checked(("ready", rel, "/tmp/x"), manual=False)
    assert "#restart" in w.update_label.text() and w.pending_update == (rel, "/tmp/x")
    w2 = window(ServiceState(True, True, True))
    w2.on_update_checked(("error", None, "offline"), manual=False)
    assert not w2.update_label.text()                    # quiet unless asked
    w2.on_update_checked(("error", None, "offline"), manual=True)
    assert "offline" in w2.update_label.text()


def test_tray_follows_the_service_state(app):
    w = window(ServiceState(True, True, True), tray=True)
    assert w.tray_toggle.text() == "Turn off" and w.tray_color == "#2e9e44"
    assert "ON" in w.tray.toolTip()
    w.backend.st = ServiceState(True, False, False)
    w.refresh()
    assert w.tray_toggle.text() == "Turn on" and w.tray_color == "#8a8a8a"
    w.tray.hide()
