import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from dpi_dashboard.config import Config  # noqa: E402
from dpi_dashboard.i18n import Translator  # noqa: E402
from dpi_dashboard.setup import runner, status  # noqa: E402
from dpi_dashboard.setup_dialog import SetupDialog  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def dialog():
    # No worker threads in tests: the status check is fed in by hand.
    return SetupDialog(Config(), Translator("en"), start_worker=lambda fn, slot: None)


def test_fresh_linux_offers_install(app):
    d = dialog()
    d.show_status(status.SetupStatus("linux", service="zapret.service", missing_auto=["curl"],
                                     resolved_active=True,
                                     dns=status.DnsCheck("discord.com", "mismatch")))
    assert d.primary.isEnabled() and d.primary.text().startswith("Install")
    assert not d.remove.isVisibleTo(d)
    assert d.dns_box.isVisibleTo(d) and d.dns_box.isChecked()   # DNS looked forged
    assert "curl" in d.summary.text() and "falsifying" in d.summary.text()


def test_package_install_offers_tune_not_remove(app):
    d = dialog()
    d.show_status(status.SetupStatus("linux", service="zapret.service", service_found=True,
                                     files_present=True, dns=status.DnsCheck("x", "ok")))
    assert d.primary.text().startswith("Find") and d.primary.isEnabled()
    assert not d.remove.isVisibleTo(d) and not d.dns_box.isChecked()


def test_foreign_windows_service_is_left_alone(app):
    d = dialog()
    d.show_status(status.SetupStatus("windows", service="GoodbyeDPI", service_found=True))
    assert not d.primary.isEnabled()
    assert "another tool" in d.log.toPlainText()


def test_managed_install_can_be_removed(app):
    d = dialog()
    d.show_status(status.SetupStatus("linux", service_found=True, files_present=True,
                                     managed=True))
    assert d.remove.isVisibleTo(d)


def test_progress_rendering(app):
    d = dialog()
    for line in ["@@STEP copy", "@@BASELINE 0/15", "@@STEP try 1", "@@TRY 1 fail",
                 "@@TRY 2 15/15", "@@CHOSEN 2 15/15", "detail line", "@@DONE ok"]:
        d.render(runner.parse_line(line))
    text = d.log.toPlainText()
    for expected in ["Copying files", "Without zapret: 0/15", "Setting 1: zapret did not start",
                     "Setting 2: 15/15", "Chosen: setting 2 (15/15)", "detail line"]:
        assert expected in text
    assert d.done_event == runner.Event("done", ("ok",))


def test_cancelled_password_prompt(app):
    d = dialog()
    d.mode, d.done_event, d.tail = "install", None, None
    d.helper_finished(126)
    assert "Cancelled" in d.log.toPlainText() and not d.result_ok


def test_dns_option_hidden_when_already_encrypted(app):
    d = dialog()
    d.show_status(status.SetupStatus("linux", service_found=True, files_present=True,
                                     resolved_active=True, dot_active=True))
    assert not d.dns_box.isVisibleTo(d)
