"""The "Setup" window: find what is missing, install zapret, pick a working strategy."""

from __future__ import annotations

import sys
from html import escape

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from . import config
from .i18n import Translator
from .setup import runner, status

GREEN, RED, AMBER = "#2e9e44", "#d23c3c", "#d08a00"


def ok(good: bool, text: str) -> str:
    """One status line with a green check or a red cross."""
    mark = "✓" if good else "✗"
    return f"<span style='color:{GREEN if good else RED}'>{mark}</span> {text}"


class SetupDialog(QDialog):
    changed = pyqtSignal()          # something was installed, retuned or removed
    line = pyqtSignal(str)          # one line of helper output, from the worker thread

    def __init__(self, cfg: config.Config, tr: Translator, parent=None, start_worker=None):
        super().__init__(parent)
        self.cfg, self.tr = cfg, tr
        self.status: status.SetupStatus | None = None
        self.done_event: runner.Event | None = None
        self.mode: str | None = None
        self.result_ok = False
        # Parent provides the thread helper so that workers outlive nothing they touch.
        self.start_worker = start_worker or parent._start
        self.setWindowTitle(tr("setup_title"))
        self.setMinimumWidth(520)

        title = QLabel(tr("setup_title"))
        f = QFont()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        title.setFont(f)
        self.summary = QLabel(tr("setup_checking"))
        self.summary.setWordWrap(True)
        self.dns_box = QCheckBox(tr("setup_dns_option"))
        self.dns_box.setVisible(False)

        self.primary = QPushButton()
        self.primary.setMinimumHeight(36)
        self.primary.setEnabled(False)
        self.primary.clicked.connect(self.on_primary)
        self.remove = QPushButton(tr("setup_remove"))
        self.remove.setVisible(False)
        self.remove.clicked.connect(self.on_remove)
        close = QPushButton(tr("close"))
        close.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(self.primary, 1)
        buttons.addWidget(self.remove)
        buttons.addWidget(close)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setVisible(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(180)

        lay = QVBoxLayout(self)
        lay.addWidget(title)
        lay.addWidget(self.summary)
        lay.addWidget(self.dns_box)
        lay.addLayout(buttons)
        lay.addWidget(self.bar)
        lay.addWidget(self.log)

        self.line.connect(self.on_line)
        self.recheck()

    # --- status ------------------------------------------------------------------------

    def recheck(self):
        self.primary.setEnabled(False)
        cfg = self.cfg
        host = cfg.hosts[0] if cfg.hosts else None
        self.start_worker(lambda: status.check(cfg.service, host), self.show_status)

    def show_status(self, st: status.SetupStatus):
        self.status = st
        tr = self.tr
        lines = []
        name = st.service or "zapret"
        lines.append(ok(st.service_found, tr("setup_service_found" if st.service_found
                                            else "setup_service_missing", service=name)))
        if st.files_present:
            lines.append(ok(True, tr("setup_files_ours" if st.managed else "setup_files_other")))
        if st.missing_required:
            items = ", ".join(st.missing_required)
            lines.append(ok(False, tr("setup_missing_required", items=items)))
        if st.missing_auto:
            lines.append(f"<span style='color:{AMBER}'>•</span> "
                         + tr("setup_missing_auto", items=", ".join(st.missing_auto)))
        if st.dns:
            key = {"ok": "setup_dns_ok", "mismatch": "setup_dns_mismatch"}.get(st.dns.state,
                                                                              "setup_dns_unknown")
            good = st.dns.state != "mismatch"
            if st.dns.state != "unknown":
                lines.append(ok(good, tr(key, host=st.dns.host)))
            else:
                detail = f" <span style='color:gray'>({escape(st.dns.error)})</span>" \
                    if st.dns.error else ""
                lines.append(f"<span style='color:{AMBER}'>?</span> "
                             f"{tr(key, host=st.dns.host)}{detail}")
        if st.dns and st.dns.state == "mismatch" and st.platform == "windows":
            lines.append(tr("setup_dns_windows_hint"))
        self.summary.setText("<br>".join(lines))

        show_dns = (st.platform == "linux" and st.resolved_active and not st.dot_active
                    and (st.can_install or st.can_tune))
        self.dns_box.setVisible(show_dns)
        self.dns_box.setChecked(show_dns and bool(st.dns) and st.dns.state == "mismatch")
        self.remove.setVisible(st.managed)
        if st.can_install:
            self.primary.setText(tr("setup_install"))
            self.primary.setEnabled(True)
        elif st.can_tune:
            self.primary.setText(tr("setup_tune"))
            self.primary.setEnabled(True)
        else:
            self.primary.setText(tr("setup_install"))
            self.primary.setEnabled(False)
            if st.service_found and not st.managed and st.platform == "windows":
                self.log.appendPlainText(tr("setup_foreign_windows"))

    # --- actions -----------------------------------------------------------------------

    def confirm(self, key: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, self.tr("setup_title"),
                          self.tr(key, tries=str(len(self.cfg.strategies)),
                                  path=self.install_path()),
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self)
        return box.exec() == QMessageBox.StandardButton.Yes

    def install_path(self) -> str:
        return str(status.windows_dir()) if sys.platform == "win32" else str(status.LINUX_DIR)

    def on_primary(self):
        st = self.status
        if st is None:
            return
        mode = "install" if st.can_install else "tune"
        if not self.confirm("setup_confirm_install" if mode == "install" else "setup_confirm_tune"):
            return
        self.begin()
        self.run_helper(mode)

    def on_remove(self):
        if not self.confirm("setup_confirm_remove"):
            return
        self.begin()
        self.run_helper("uninstall")

    def run_helper(self, mode: str):
        self.mode, self.done_event = mode, None
        try:
            inv = runner.build(mode, strategies=self.cfg.strategies, hosts=self.cfg.hosts,
                               tries=self.cfg.tries,
                               dns_dot=self.dns_box.isVisible() and self.dns_box.isChecked())
        except ValueError as e:
            self.finish(False, self.tr("error", msg=str(e)))
            return
        self.say(self.tr("auth_hint"))
        emit = self.line.emit           # queued into the UI thread

        def call():
            try:
                return runner.run(inv, emit)
            except OSError as e:
                return e
        self.start_worker(call, self.helper_finished)

    def on_line(self, line: str):
        self.render(runner.parse_line(line))

    def render(self, ev: runner.Event):
        tr = self.tr
        a = ev.args
        if ev.kind == "step":
            key = a[0] if a else ""
            if key == "verified":
                self.say(tr("step_verified", version=a[1] if len(a) > 1 else "?"))
            elif key != "try":
                self.say(tr(f"step_{key}") if f"step_{key}" in tr.keys() else key)
        elif ev.kind == "baseline":
            self.say(tr("setup_baseline", score=a[0] if a else "?"))
        elif ev.kind in ("try", "chosen") and len(a) == 2:
            n, score = a
            key = "setup_try_fail" if score == "fail" else f"setup_{ev.kind}"
            self.say(tr(key, n=n, score=score))
        elif ev.kind == "warn":
            self.say(tr(f"warn_{a[0]}") if a and f"warn_{a[0]}" in tr.keys() else " ".join(a))
        elif ev.kind == "error":
            self.say(tr("error", msg=" ".join(a)), RED)
        elif ev.kind == "done":
            self.done_event = ev
        elif a and a[0].strip():
            self.log.appendPlainText("    " + a[0])

    def helper_finished(self, rc):
        done = self.done_event
        if isinstance(rc, Exception):
            self.finish(False, self.tr("error", msg=str(rc)))
        elif done and done.args[:1] == ("ok",):
            self.finish(True, self.tr("setup_removed" if self.mode == "uninstall"
                                      else "setup_success"))
        elif done is None and rc in runner.CANCELLED_CODES:
            self.finish(False, self.tr("cancelled"))
        elif done is None:
            self.finish(False, self.tr("setup_no_output", code=str(rc)))
        else:
            self.finish(False, self.tr("setup_failed"))

    # --- helpers -----------------------------------------------------------------------

    def begin(self):
        self.primary.setEnabled(False)
        self.remove.setEnabled(False)
        self.dns_box.setEnabled(False)
        self.bar.setVisible(True)
        self.log.clear()

    def finish(self, ok: bool, message: str):
        self.result_ok = ok
        self.bar.setVisible(False)
        self.remove.setEnabled(True)
        self.dns_box.setEnabled(True)
        self.say(message, GREEN if ok else RED)
        self.changed.emit()
        self.recheck()

    def say(self, text: str, color: str | None = None):
        if color:
            self.log.appendHtml(f"<span style='color:{color}'><b>{text}</b></span>")
        else:
            self.log.appendPlainText(text)
