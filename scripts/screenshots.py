"""Render the README screenshots from the real widgets, with a fake service state.

    PYTHONPATH=src python scripts/screenshots.py [docs/screenshots]

Nothing is shown on screen and no service is touched. Colors are fixed to Breeze Light so
the pictures do not depend on the desktop theme; the widget style and icons come from the
desktop running the script (the committed shots were made on KDE Plasma).
"""
import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

from dpi_dashboard import app as appmod
from dpi_dashboard.backends import Backend, ServiceState, ToggleResult
from dpi_dashboard.config import Config
from dpi_dashboard.i18n import Translator
from dpi_dashboard.probe import Attempt, HostResult
from dpi_dashboard.setup import runner, status
from dpi_dashboard.setup_dialog import SetupDialog
from dpi_dashboard.updater import Release

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
qapp = QApplication.instance() or QApplication(sys.argv)
from PyQt6.QtGui import QPalette  # noqa: E402


def light_palette() -> QPalette:
    """Breeze Light colors, so the shots do not depend on the desktop theme."""
    pal = QPalette()
    R = QPalette.ColorRole
    for role, c in [(R.Window, "#eff0f1"), (R.WindowText, "#232629"), (R.Base, "#fcfcfc"),
                    (R.AlternateBase, "#f7f7f7"), (R.Text, "#232629"), (R.Button, "#fcfcfc"),
                    (R.ButtonText, "#232629"), (R.Highlight, "#3daee9"),
                    (R.HighlightedText, "#ffffff"), (R.Link, "#2980b9"), (R.ToolTipBase, "#f7f7f7"),
                    (R.ToolTipText, "#232629"), (R.PlaceholderText, "#707d8a"),
                    (R.Light, "#ffffff"), (R.Midlight, "#f5f5f5"), (R.Mid, "#babfc4"),
                    (R.Dark, "#8c9196"), (R.Shadow, "#474a4c")]:
        pal.setColor(role, QColor(c))
    pal.setColor(QPalette.ColorGroup.Disabled, R.Text, QColor("#a0a4a8"))
    pal.setColor(QPalette.ColorGroup.Disabled, R.ButtonText, QColor("#a0a4a8"))
    pal.setColor(QPalette.ColorGroup.Disabled, R.WindowText, QColor("#a0a4a8"))
    return pal


qapp.setPalette(light_palette())
appmod.updater.install_kind = lambda: "exe"          # show the self-update notice


class Fake(Backend):
    def __init__(self, kind, service, st):
        super().__init__(service, runner=None)
        self.kind, self.st = kind, st

    def state(self):
        return self.st

    def set_enabled(self, on):
        return ToggleResult(True)


HOSTS = Config().hosts


def results(ok_counts, reason="reset"):
    return [HostResult(h, [Attempt(True)] * n + [Attempt(False, reason)] * (3 - n))
            for h, n in zip(HOSTS, ok_counts, strict=True)]


def window(lang, kind, service, st, res=None, update=None):
    w = appmod.Dashboard(Fake(kind, service, st), Config(), Translator(lang), tray=False)
    if res:
        w.show_results(res)
    if update:
        w.on_update_checked(update, manual=False)
    w.resize(440, w.sizeHint().height())
    w.adjustSize()
    return w


def save(widget, name):
    widget.ensurePolished()
    pm = widget.grab()
    pm.save(str(OUT / name))
    print(name, pm.width(), pm.height())


def menu_shot(w, name):
    """The window with the Settings menu open below its button."""
    base = w.grab()
    menu = w.settings_btn.menu()
    w.sync_autostart = lambda: None
    w.autostart_action.blockSignals(True)     # only the tick: never touch the real autostart
    w.autostart_action.setChecked(True)
    w.autostart_action.blockSignals(False)
    menu.adjustSize()
    mp = menu.grab()
    pos = w.settings_btn.mapTo(w, QPoint(w.settings_btn.width() - mp.width(),
                                         w.settings_btn.height()))
    width = max(base.width(), pos.x() + mp.width())
    height = max(base.height(), pos.y() + mp.height() + 4)
    canvas = QPixmap(width, height)
    canvas.fill(w.palette().window().color())
    p = QPainter(canvas)
    p.drawPixmap(0, 0, base)
    p.setPen(QColor(0, 0, 0, 60))
    p.drawRect(pos.x(), pos.y(), mp.width(), mp.height())
    p.drawPixmap(pos, mp)
    p.end()
    canvas.save(str(OUT / name))
    print(name, width, height)


def tray_strip(name):
    size, gap = 64, 24
    canvas = QPixmap(3 * size + 2 * gap, size)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    for i, c in enumerate((appmod.GREEN, appmod.GRAY, appmod.RED)):
        p.drawPixmap(i * (size + gap), 0, appmod.tray_icon(c).pixmap(size, size))
    p.end()
    canvas.save(str(OUT / name))
    print(name)


def setup_shot(lang, platform, name):
    tr = Translator(lang)
    d = SetupDialog(Config(), tr, start_worker=lambda fn, slot: None)
    d.show_status(status.SetupStatus(platform, service="zapret" if platform == "windows"
                                     else "zapret.service", service_found=True,
                                     files_present=True, managed=True,
                                     resolved_active=platform == "linux",
                                     dns=status.DnsCheck("discord.com", "mismatch")))
    d.begin()
    lines = ["@@STEP download", "@@STEP verified v72.13", "@@STEP copy", "@@STEP unit",
             "@@STEP dns", "@@STEP baseline", "@@BASELINE 4/18", "@@STEP try 1",
             "@@TRY 1 18/18", "@@CHOSEN 1 18/18", "@@DONE ok"]
    for line in lines:
        d.render(runner.parse_line(line))
    d.mode = "install"
    d.start_worker = lambda fn, slot: None
    d.finish(True, tr("setup_success"))
    d.show_status(status.SetupStatus(platform, service="zapret" if platform == "windows"
                                     else "zapret.service", service_found=True,
                                     files_present=True, managed=True,
                                     dns=status.DnsCheck("discord.com", "ok")))
    d.resize(560, 470)
    save(d, name)


for lang in ("en", "tr"):
    win = ("windows-service", "zapret")
    lin = ("systemd", "zapret.service")
    save(window(lang, *lin, ServiceState(True, True, True), results([3] * 6)),
         f"main-linux-{lang}.png")
    save(window(lang, *win, ServiceState(True, True, True), results([3] * 6)),
         f"main-windows-{lang}.png")
    save(window(lang, *win, ServiceState(True, False, False), results([1, 0, 2, 3, 0, 1])),
         f"blocked-{lang}.png")
    save(window(lang, *win, ServiceState(False)), f"missing-{lang}.png")
    rel = Release("v0.6.0", "0.6.0", "https://github.com/hamer1818/dpi-dashboard/releases", None,
                  None)
    save(window(lang, *win, ServiceState(True, True, True), results([3] * 6),
                update=("ready", rel, Path("x"))), f"update-{lang}.png")
    menu_shot(window(lang, *win, ServiceState(True, True, True), results([3] * 6)),
              f"settings-menu-{lang}.png")
    setup_shot(lang, "windows", f"setup-windows-{lang}.png")
    setup_shot(lang, "linux", f"setup-linux-{lang}.png")
tray_strip("tray-icons.png")
