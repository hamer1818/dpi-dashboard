"""The DPI Dashboard window."""

from __future__ import annotations

import getpass
import subprocess
import sys
from importlib.resources import files

from PyQt6.QtCore import QRectF, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from . import __version__, autostart, config, updater
from .backends import Backend, ServiceState, ToggleResult, detect_backend
from .i18n import Translator
from .probe import HostResult, check_hosts

GREEN, RED, AMBER, GRAY = "#2e9e44", "#d23c3c", "#d08a00", "#8a8a8a"
REPO = "https://github.com/hamer1818/dpi-dashboard"
UPDATE_INTERVAL_MS = 12 * 3600 * 1000


def icon() -> QIcon:
    themed = QIcon.fromTheme("dpi-dashboard")
    if not themed.isNull():
        return themed
    return QIcon(str(files("dpi_dashboard") / "assets" / "icon.svg"))


def tray_icon(color: str) -> QIcon:
    """The app icon with a status dot in the corner."""
    pm = icon().pixmap(64, 64)
    if pm.isNull():
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("white"))
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(36, 36, 26, 26))
    p.end()
    return QIcon(pm)


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
                 warning: str | None = None, tray: bool | None = None,
                 check_updates: bool = False):
        super().__init__()
        self.backend, self.cfg, self.tr = backend, cfg, tr
        self.busy = False
        self.workers: list[Worker] = []
        self.quitting = False
        self.tray_color = ""
        self.update_kind = updater.install_kind()
        self.pending_update = None          # (Release, downloaded file) waiting for a restart
        self.updating = False

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
        self.settings_btn.setMenu(self.settings_menu())
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
        self.update_label = QLabel()
        self.update_label.setWordWrap(True)
        self.update_label.setVisible(False)
        self.update_label.linkActivated.connect(self.on_update_link)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addLayout(head)
        lay.addWidget(self.toggle_btn)
        lay.addWidget(line)
        lay.addLayout(buttons)
        lay.addLayout(grid)
        lay.addWidget(self.msg)
        lay.addWidget(self.update_label)
        lay.addStretch(1)
        # The GPL asks interactive programs to show where the license can be read.
        self.about = QLabel(f"<a href='#about'>{tr('about_link')}</a>")
        self.about.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.about.linkActivated.connect(self.show_about)
        lay.addWidget(self.about)

        if tray is None:
            tray = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = self.make_tray() if tray else None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(int(cfg.refresh_seconds * 1000))
        self.refresh()
        if check_updates:
            self.update_timer = QTimer(self)
            self.update_timer.timeout.connect(self.check_updates)
            self.update_timer.start(UPDATE_INTERVAL_MS)
            QTimer.singleShot(3000, self.check_updates)

    # --- tray and menus ----------------------------------------------------------------

    def make_tray(self) -> QSystemTrayIcon:
        tr = self.tr
        t = QSystemTrayIcon(icon(), self)
        menu = QMenu(self)
        menu.addAction(tr("tray_show"), self.bring_to_front)
        self.tray_toggle = menu.addAction(tr("turn_on"), self.on_toggle)
        menu.addAction(tr("test"), self.tray_test)
        menu.addSeparator()
        menu.addAction(tr("tray_quit"), self.quit_app)
        t.setContextMenu(menu)
        t.activated.connect(self.on_tray_activated)
        t.setToolTip("DPI Dashboard")
        t.show()
        return t

    def settings_menu(self) -> QMenu:
        tr = self.tr
        m = QMenu(self)
        self.autostart_action = m.addAction(tr("opt_autostart"))
        self.autostart_action.setCheckable(True)
        self.autostart_action.toggled.connect(self.set_autostart)
        self.tray_action = m.addAction(tr("opt_close_to_tray"))
        self.tray_action.setCheckable(True)
        self.tray_action.setChecked(self.cfg.close_to_tray)
        self.tray_action.toggled.connect(lambda on: self.set_option("close_to_tray", on))
        self.update_action = m.addAction(tr("opt_auto_update"))
        self.update_action.setCheckable(True)
        self.update_action.setChecked(self.cfg.auto_update)
        self.update_action.toggled.connect(lambda on: self.set_option("auto_update", on))
        m.addAction(tr("check_updates"), lambda: self.check_updates(manual=True))
        m.addSeparator()
        m.addAction(tr("open_settings_file"), self.open_settings)
        m.aboutToShow.connect(self.sync_autostart)
        return m

    def sync_autostart(self):
        try:
            on = autostart.is_enabled()
        except OSError:
            on = False
        self.autostart_action.blockSignals(True)
        self.autostart_action.setChecked(on)
        self.autostart_action.blockSignals(False)

    def set_autostart(self, on: bool):
        try:
            autostart.set_enabled(on)
        except OSError as e:
            self.msg.setText(f"<span style='color:{RED}'>{self.tr('error', msg=str(e))}</span>")
            self.sync_autostart()

    def set_option(self, key: str, value):
        setattr(self.cfg, key, value)
        try:
            config.set_value(key, value)
        except OSError as e:
            self.msg.setText(f"<span style='color:{RED}'>{self.tr('error', msg=str(e))}</span>")

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.bring_to_front()

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def tray_test(self):
        self.bring_to_front()
        self.run_test()

    def closeEvent(self, event):
        if self.quitting or not (self.tray and self.cfg.close_to_tray):
            self.quitting = True
            event.accept()
            QApplication.instance().quit()
            return
        event.ignore()
        self.hide()
        if not getattr(self, "told_tray", False):
            self.told_tray = True
            self.tray.showMessage("DPI Dashboard", self.tr("tray_still_running"),
                                  QSystemTrayIcon.MessageIcon.Information, 4000)

    def quit_app(self):
        self.quitting = True
        QApplication.instance().quit()

    def update_tray(self, color: str, text: str):
        if self.tray is None:
            return
        if color != self.tray_color:
            self.tray_color = color
            self.tray.setIcon(tray_icon(color))
        self.tray.setToolTip(f"DPI Dashboard: {text}")

    # --- updates -----------------------------------------------------------------------

    def check_updates(self, manual: bool = False):
        if self.updating or self.pending_update:
            if manual and self.pending_update:
                self.show_update_ready()
            return
        self.updating = True
        if manual:
            self.update_label.setText(self.tr("update_checking"))
            self.update_label.setVisible(True)
        kind = self.update_kind if self.cfg.auto_update else None

        def work():
            try:
                rel = updater.check(kind=self.update_kind)
                if rel is None:
                    return ("none", None, None)
                if kind and rel.asset:
                    path = updater.download(rel, updater.download_path(kind, rel))
                    return ("ready", rel, path)
                return ("available", rel, None)
            except (OSError, ValueError, updater.UpdateError) as e:
                return ("error", None, str(e))
        self._start(work, lambda r: self.on_update_checked(r, manual))

    def on_update_checked(self, result, manual: bool):
        self.updating = False
        what, rel, extra = result
        tr = self.tr
        if what == "ready":
            self.pending_update = (rel, extra)
            self.show_update_ready()
            if self.tray and not self.isVisible():
                self.tray.showMessage("DPI Dashboard", tr("update_ready_tray", version=rel.version),
                                      QSystemTrayIcon.MessageIcon.Information, 6000)
        elif what == "available":
            self.update_label.setText(tr("update_available", version=rel.version,
                                         page=rel.page or f"{REPO}/releases/latest"))
            self.update_label.setVisible(True)
        elif manual:
            self.update_label.setText(tr("update_none") if what == "none"
                                      else tr("update_failed", msg=extra))
            self.update_label.setVisible(True)

    def show_update_ready(self):
        rel = self.pending_update[0]
        self.update_label.setText(self.tr("update_ready", version=rel.version))
        self.update_label.setVisible(True)

    def on_update_link(self, link: str):
        if link == "#restart":
            self.restart_for_update()
        else:
            QDesktopServices.openUrl(QUrl(link))

    def apply_pending_update(self) -> bool:
        if not self.pending_update or not self.update_kind:
            return False
        _, path = self.pending_update
        self.pending_update = None
        try:
            updater.apply(self.update_kind, path)
            return True
        except updater.UpdateError as e:
            self.update_label.setText(self.tr("update_failed", msg=str(e)))
            self.update_label.setVisible(True)
            return False

    def restart_for_update(self):
        if self.busy:
            return
        if not self.apply_pending_update():
            return
        server = QApplication.instance().property("instance_server")
        if isinstance(server, QLocalServer):
            server.close()            # so the new program does not hand over to this one
        try:
            subprocess.Popen(autostart.launch_command(), close_fds=True)
        except OSError as e:
            self.update_label.setText(self.tr("error", msg=str(e)))
            return
        self.quit_app()

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
            self.update_tray(RED, tr("missing"))
            if self.tray:
                self.tray_toggle.setText(tr("turn_on"))
                self.tray_toggle.setEnabled(False)
            return
        self.dot.setStyleSheet(f"color: {GREEN if st.active else GRAY};")
        self.state_label.setText(tr("on") if st.active else tr("off"))
        boot = tr("boot_on") if st.enabled else tr("boot_off")
        self.detail.setText(f"{self.backend.label} · {boot}")
        if not self.busy:
            self.toggle_btn.setText(tr("turn_off") if st.active else tr("turn_on"))
            self.toggle_btn.setEnabled(True)
        self.update_tray(GREEN if st.active else GRAY, tr("on") if st.active else tr("off"))
        if self.tray:
            self.tray_toggle.setText(tr("turn_off") if st.active else tr("turn_on"))
            self.tray_toggle.setEnabled(not self.busy)

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


def instance_name() -> str:
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = "user"
    return f"dpi-dashboard-{''.join(c for c in user if c.isalnum()) or 'user'}"


def hand_over_to_running() -> bool:
    """If DPI Dashboard already runs for this user, ask it to show its window."""
    sock = QLocalSocket()
    sock.connectToServer(instance_name())
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show\n")
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main(argv: list[str] | None = None):
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"dpi-dashboard {__version__}")
        return
    self_test = "--self-test" in argv
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
    if not self_test and hand_over_to_running():
        return
    updater.cleanup()
    autostart.refresh()
    win = Dashboard(backend, cfg, tr, warning, check_updates=not self_test)
    if win.tray:
        app.setQuitOnLastWindowClosed(False)
    if not self_test:
        server = QLocalServer(app)
        QLocalServer.removeServer(instance_name())      # left over after a crash (Linux)
        if server.listen(instance_name()):
            server.newConnection.connect(lambda: (server.nextPendingConnection(),
                                                  win.bring_to_front()))
            app.setProperty("instance_server", server)
    if "--minimized" in argv:
        if win.tray is None:
            win.showMinimized()
    else:
        win.show()
    app.aboutToQuit.connect(win.apply_pending_update)
    if self_test:                    # used by CI to check that a packaged build starts
        app.processEvents()
        sys.exit(0 if win.state_label.text() else 1)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
