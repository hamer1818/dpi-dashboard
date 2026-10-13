"""The DPI Dashboard window."""

from __future__ import annotations

import sys
from importlib.resources import files

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__, config
from .backends import Backend, ServiceState, ToggleResult, detect_backend
from .i18n import Translator
from .probe import HostResult, check_hosts

GREEN, RED, AMBER, GRAY = "#2e9e44", "#d23c3c", "#d08a00", "#8a8a8a"
REPO = "https://github.com/hamer1818/dpi-dashboard"


def icon() -> QIcon:
    themed = QIcon.fromTheme("dpi-dashboard")
    if not themed.isNull():
        return themed
    return QIcon(str(files("dpi_dashboard") / "assets" / "icon.svg"))


class Worker(QThread):
    """Runs one blocking call off the UI thread."""

    result = pyqtSignal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        self.result.emit(self.fn())


def _scaled_font(delta: int, bold: bool = False) -> QFont:
    f = QFont()
    f.setPointSize(f.pointSize() + delta)
    f.setBold(bold)
    return f


class Dashboard(QWidget):
    def __init__(self, backend: Backend | None, cfg: config.Config, tr: Translator,
                 warning: str | None = None):
        super().__init__()
        self.backend, self.cfg, self.tr = backend, cfg, tr
        self.busy = False
        self.workers: list[Worker] = []

        self.setWindowTitle("DPI Dashboard")
        self.setWindowIcon(icon())
        self.setMinimumWidth(400)

        title = QLabel(tr("title"))
        title.setFont(_scaled_font(3, bold=True))
        self.dot = QLabel("●")
        self.dot.setFont(_scaled_font(10))
        self.state_label = QLabel()
        self.state_label.setFont(_scaled_font(6, bold=True))
        self.detail = QLabel()
        self.detail.setStyleSheet(f"color: {GRAY};")
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        head = QHBoxLayout()
        head.addWidget(self.dot)
        col = QVBoxLayout()
        col.addWidget(self.state_label)
        col.addWidget(self.detail)
        head.addLayout(col)
        head.addStretch(1)

        self.toggle_btn = QPushButton()
        self.toggle_btn.setMinimumHeight(40)
        self.toggle_btn.clicked.connect(self.on_toggle)

        self.test_btn = QPushButton(QIcon.fromTheme("view-refresh"), tr("test"))
        self.test_btn.clicked.connect(self.run_test)
        self.setup_btn = QPushButton(QIcon.fromTheme("run-build-install"), tr("setup_btn"))
        self.setup_btn.clicked.connect(self.open_setup)
        self.settings_btn = QPushButton(QIcon.fromTheme("configure"), tr("settings"))
        self.settings_btn.clicked.connect(self.open_settings)
        buttons = QHBoxLayout()
        buttons.addWidget(self.test_btn, 1)
        buttons.addWidget(self.setup_btn)
        buttons.addWidget(self.settings_btn)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        grid = QGridLayout()
        self.result_labels: dict[str, QLabel] = {}
        for i, host in enumerate(cfg.hosts):
            val = QLabel("–")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(QLabel(host), i, 0)
            grid.addWidget(val, i, 1)
            self.result_labels[host] = val
        self.msg = QLabel(tr("config_warning", msg=warning) if warning else "")
        self.msg.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addLayout(head)
        lay.addWidget(self.toggle_btn)
        lay.addWidget(line)
        lay.addLayout(buttons)
        lay.addLayout(grid)
        lay.addWidget(self.msg)
        lay.addStretch(1)
        # The GPL asks interactive programs to show where the license can be read.
        self.about = QLabel(f"<a href='#about'>{tr('about_link')}</a>")
        self.about.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.about.linkActivated.connect(self.show_about)
        lay.addWidget(self.about)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(int(cfg.refresh_seconds * 1000))
        self.refresh()

    # --- state -------------------------------------------------------------------------

    def current_state(self) -> ServiceState | None:
        if self.backend is None:
            return None
        try:
            return self.backend.state()
        except Exception:  # a broken service manager must not take the window down
            return ServiceState(installed=False)

    def refresh(self):
        st = self.current_state()
        tr = self.tr
        if st is None or not st.installed:
            self.dot.setStyleSheet(f"color: {RED};")
            self.state_label.setText(tr("missing"))
            self.detail.setText(self.backend.label if self.backend else "")
            if not self.busy:
                self.toggle_btn.setText(tr("turn_on"))
                self.toggle_btn.setEnabled(False)
            if not self.msg.text():
                self.msg.setText(tr("no_backend") if self.backend is None
                                 else tr("not_installed", service=self.backend.service))
            return
        self.dot.setStyleSheet(f"color: {GREEN if st.active else GRAY};")
        self.state_label.setText(tr("on") if st.active else tr("off"))
        boot = tr("boot_on") if st.enabled else tr("boot_off")
        self.detail.setText(f"{self.backend.label} · {boot}")
        if not self.busy:
            self.toggle_btn.setText(tr("turn_off") if st.active else tr("turn_on"))
            self.toggle_btn.setEnabled(True)

    # --- actions -----------------------------------------------------------------------

    def _start(self, fn, slot):
        w = Worker(fn, self)
        w.result.connect(slot)
        w.finished.connect(lambda: self.workers.remove(w))
        self.workers.append(w)
        w.start()

    def on_toggle(self):
        st = self.current_state()
        if not st or not st.installed or self.busy:
            return
        turn_on = not st.active
        self.busy = True
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.setText(self.tr("turning_on") if turn_on else self.tr("turning_off"))
        self.msg.setText(self.tr("auth_hint"))
        backend = self.backend
        self._start(lambda: (turn_on, backend.set_enabled(turn_on)), self.on_toggled)

    def on_toggled(self, payload: tuple[bool, ToggleResult]):
        turned_on, res = payload
        self.busy = False
        if res.ok:
            self.msg.setText("")
            if turned_on:
                self.run_test()
        elif res.cancelled:
            self.msg.setText(f"<span style='color:{RED}'>{self.tr('cancelled')}</span>")
        else:
            self.msg.setText(f"<span style='color:{RED}'>"
                             f"{self.tr('error', msg=res.message or '?')}</span>")
        self.refresh()

    def run_test(self):
        if not self.test_btn.isEnabled() or not self.cfg.hosts:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText(self.tr("testing"))
        for v in self.result_labels.values():
            v.setText("…")
            v.setStyleSheet("")
            v.setToolTip("")
        hosts, tries, timeout = list(self.cfg.hosts), self.cfg.tries, self.cfg.timeout
        self._start(lambda: check_hosts(hosts, tries, timeout), self.show_results)

    def show_results(self, results: list[HostResult]):
        tries = self.cfg.tries
        good = 0
        for r in results:
            ok = r.successes
            color = GREEN if ok == tries else (RED if ok == 0 else AMBER)
            label = self.result_labels[r.host]
            label.setText(f"{ok}/{tries}")
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            label.setToolTip("\n".join(self.tr(f"reason_{x}") for x in r.reasons))
            good += ok == tries
        self.msg.setText(self.tr("all_ok") if good == len(results) else self.tr("some_blocked"))
        self.test_btn.setText(self.tr("test"))
        self.test_btn.setEnabled(True)

    def open_setup(self):
        from .setup_dialog import SetupDialog
        dlg = SetupDialog(self.cfg, self.tr, self)
        dlg.changed.connect(self.reload_backend)
        dlg.exec()

    def reload_backend(self):
        """Look for the service again, e.g. after the setup installed it."""
        try:
            self.backend = detect_backend(self.cfg.backend, self.cfg.service)
        except ValueError:
            self.backend = None
        self.msg.setText("")
        self.refresh()

    def about_text(self) -> str:
        return self.tr("about_text", version=__version__, repo=REPO,
                       notices=f"{REPO}/blob/v{__version__}/THIRD_PARTY_NOTICES.md")

    def show_about(self, _link: str = ""):
        box = QMessageBox(self)
        box.setWindowTitle(self.tr("about_title"))
        box.setIconPixmap(icon().pixmap(64, 64))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        box.setText(self.about_text())
        box.exec()

    def open_settings(self):
        path = config.ensure_file()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def main(argv: list[str] | None = None):
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"dpi-dashboard {__version__}")
        return
    cfg, warning = config.load()
    tr = Translator(cfg.language)
    try:
        backend = detect_backend(cfg.backend, cfg.service)
    except ValueError as e:          # e.g. an invalid service name in the settings
        backend, warning = None, str(e)
    app = QApplication(argv)
    app.setApplicationName("DPI Dashboard")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("dpi-dashboard")
    app.setWindowIcon(icon())
    win = Dashboard(backend, cfg, tr, warning)
    win.show()
    if "--self-test" in argv:        # used by CI to check that a packaged build starts
        app.processEvents()
        sys.exit(0 if win.state_label.text() else 1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
