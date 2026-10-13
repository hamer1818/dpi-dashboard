"""Run the privileged setup helper and follow its progress."""

from __future__ import annotations

import base64
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .strategies import is_safe

# Helper -> app protocol, one line each, written to the log file:
#   @@STEP <key>            @@BASELINE <ok>/<max>     @@TRY <n> <ok>/<max>|fail
#   @@CHOSEN <n> <ok>/<max> @@WARN <key>              @@ERROR <text>     @@DONE ok|fail
# Any other line is free-form detail.


@dataclass(frozen=True)
class Event:
    kind: str          # "step", "baseline", "try", "chosen", "warn", "error", "done", "text"
    args: tuple[str, ...]


def parse_line(line: str) -> Event:
    line = line.lstrip("\ufeff").rstrip("\r\n")
    if line.startswith("@@"):
        head, _, rest = line[2:].partition(" ")
        return Event(head.lower(), tuple(rest.split(" ", 1)) if rest else ())
    return Event("text", (line,))


class LogTail:
    """Reads the lines appended to a file since the last call."""

    def __init__(self, path: Path):
        self.path, self.pos, self.buf = path, 0, ""

    def read(self) -> list[str]:
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                f.seek(self.pos)
                data = f.read()
                self.pos = f.tell()
        except OSError:
            return []
        self.buf += data
        *lines, self.buf = self.buf.split("\n")
        return lines


def workdir() -> Path:
    """A private (0700) directory for the download, the helper copy and the log."""
    return Path(tempfile.mkdtemp(prefix="dpi-dashboard-setup-"))


def stage_helper(dest: Path) -> Path:
    """Copy the helper script out of the package into the private work directory."""
    name = "setup-windows.ps1" if sys.platform == "win32" else "setup-linux.sh"
    target = dest / name
    shutil.copyfile(files("dpi_dashboard") / "assets" / name, target)
    return target


def write_strategies(dest: Path, strategies: list[str]) -> Path:
    safe = [s.strip() for s in strategies if is_safe(s.strip())]
    if not safe:
        raise ValueError("no valid strategies")
    path = dest / "strategies.txt"
    path.write_text("\n".join(safe) + "\n", encoding="utf-8")
    return path


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def build_command(helper: Path, mode: str, log: Path, *, source: Path | None = None,
                  strategies: Path | None = None, hosts: list[str] = (), tries: int = 3,
                  dns_dot: bool = False, elevate: str = "auto") -> list[str]:
    """elevate: "auto" (pkexec / UAC), "sudo" (Linux terminal) or "none" (already admin)."""
    if sys.platform == "win32":
        args = ["-Mode", mode, "-Log", str(log), "-Tries", str(tries),
                "-Hosts", ",".join(hosts)]
        if source:
            args += ["-Source", str(source)]
        if strategies:
            args += ["-Strategies", str(strategies)]
        direct = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                  "-File", str(helper), *args]
        if elevate == "none":
            return direct
        # Parameter names must stay bare: PowerShell binds a quoted '-Mode' as a plain string.
        named = " ".join(f"{args[i]} {_ps_quote(args[i + 1])}" for i in range(0, len(args), 2))
        # The elevated process has no console the app can read, so anything that fails
        # before the helper starts logging is written to the log here.
        inner = (f"try {{ & {_ps_quote(str(helper))} {named}; exit $LASTEXITCODE }} "
                 f"catch {{ [IO.File]::AppendAllText({_ps_quote(str(log))}, "
                 "\"@@ERROR $($_.Exception.Message)`n@@DONE fail`n\"); exit 1 }")
        enc = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
        outer = ("try { $p = Start-Process powershell -Verb RunAs -Wait -PassThru "
                 "-WindowStyle Hidden -ArgumentList '-NoProfile','-NonInteractive',"
                 f"'-ExecutionPolicy','Bypass','-EncodedCommand','{enc}'; exit $p.ExitCode }}"
                 " catch { exit 1223 }")
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", outer]

    cmd = ["/bin/bash", str(helper), mode, str(log), "--tries", str(tries),
           "--hosts", " ".join(hosts)]
    if source:
        cmd += ["--source", str(source)]
    if strategies:
        cmd += ["--strategies", str(strategies)]
    if dns_dot:
        cmd.append("--dns-dot")
    if elevate == "auto" and os.geteuid() != 0:
        return ["pkexec", *cmd]
    if elevate == "sudo":
        return ["sudo", *cmd]
    return cmd


# Exit codes that mean "the user said no" rather than "it failed".
CANCELLED_CODES = (126, 127, 1223)
