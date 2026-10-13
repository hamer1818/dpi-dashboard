"""Start the privileged setup helper and follow its progress.

Security boundary: the helper runs as root / administrator, so it must not execute or
trust anything a normal user can write. The script is therefore never written to disk:

- Linux: the script is piped into ``pkexec /bin/bash -c '<bootstrap>'``; the bootstrap
  reads it from stdin and runs it. Progress comes back on stdout.
- Windows: the script is gzip-compressed and embedded in the elevated PowerShell command
  line. The helper logs to %ProgramData%\\dpi-dashboard\\logs, a folder it locks so users
  can read but not write; the app follows that file.

The helpers download and verify zapret themselves, in folders only root can write.
"""

from __future__ import annotations

import base64
import gzip
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from ..backends.base import _NO_WINDOW
from .strategies import is_safe

# Helper -> app protocol, one line each:
#   @@STEP <key> [arg]     @@BASELINE <ok>/<max>   @@TRY <n> <ok>/<max>|fail
#   @@CHOSEN <n> <ok>/<max> @@WARN <key>           @@ERROR <text>    @@DONE ok|fail
# Any other line is free-form detail.

LINUX_BOOTSTRAP = 'script=$(cat) && exec /bin/bash -c "$script" dpi-dashboard-setup "$@" </dev/null'
# CreateProcess limits a command line to 32767 characters.
WINDOWS_COMMAND_LIMIT = 32000
# Exit codes that mean "the user said no" rather than "it failed".
CANCELLED_CODES = (126, 127, 1223)


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


@dataclass(frozen=True)
class Invocation:
    args: list[str]
    stdin: bytes | None = None     # Linux: the helper script
    log: Path | None = None        # Windows: the file the elevated helper writes to


def helper_text(name: str) -> str:
    return (files("dpi_dashboard") / "assets" / name).read_text(encoding="utf-8")


def valid_strategies(strategies) -> list[str]:
    safe = [s.strip() for s in strategies if is_safe(s.strip())]
    if not safe:
        raise ValueError("no valid strategies")
    return safe


def windows_log_path(name: str) -> Path:
    base = os.environ.get("ProgramData") or r"C:\ProgramData"
    return Path(base) / "dpi-dashboard" / "logs" / f"{name}.log"


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _windows_inner(params: dict[str, str]) -> str:
    packed = base64.b64encode(gzip.compress(helper_text("setup-windows.ps1").encode("utf-8"),
                                            mtime=0)).decode("ascii")
    named = " ".join(f"-{k} {_ps_quote(v)}" for k, v in params.items())
    # Before any cmdlet runs: PowerShell autoloads modules from PSModulePath, which
    # includes the user's own Documents\WindowsPowerShell\Modules. An elevated session
    # must only load the system's modules. The folders come from the OS, not from
    # environment variables the user controls. (Windows PowerShell only; pwsh in tests.)
    return ("if ($PSVersionTable.PSEdition -eq 'Desktop') { $env:PSModulePath = "
            "[Environment]::GetFolderPath('ProgramFiles') + '\\WindowsPowerShell\\Modules;' + "
            "[Environment]::GetFolderPath('System') + '\\WindowsPowerShell\\v1.0\\Modules' }; "
            "$ErrorActionPreference = 'Stop'; "
            f"$b = [Convert]::FromBase64String('{packed}'); "
            "$z = New-Object IO.Compression.GZipStream((New-Object IO.MemoryStream(,$b)), "
            "[IO.Compression.CompressionMode]::Decompress); "
            "$code = (New-Object IO.StreamReader($z, [Text.Encoding]::UTF8)).ReadToEnd(); "
            f"& ([ScriptBlock]::Create($code)) {named}; exit $LASTEXITCODE")


def _encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def build(mode: str, *, strategies=(), hosts=(), tries: int = 3, dns_dot: bool = False,
          elevate: str = "auto", log_name: str | None = None) -> Invocation:
    """elevate: "auto" (pkexec / UAC), "sudo" (Linux terminal) or "none" (already admin)."""
    strategies = valid_strategies(strategies) if mode != "uninstall" else []
    if sys.platform == "win32":
        name = log_name or uuid.uuid4().hex
        enc = _encode(_windows_inner({"Mode": mode, "LogName": name,
                                      "Hosts": ",".join(hosts), "Tries": str(tries),
                                      "Strategies": "|".join(strategies)}))
        if elevate == "none":
            args = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", enc]
        else:
            outer = ("try { $p = Start-Process powershell -Verb RunAs -Wait -PassThru "
                     "-WindowStyle Hidden -ArgumentList '-NoProfile','-NonInteractive',"
                     f"'-ExecutionPolicy','Bypass','-EncodedCommand','{enc}'; exit $p.ExitCode }}"
                     " catch { exit 1223 }")
            args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", outer]
        if len(subprocess.list2cmdline(args)) > WINDOWS_COMMAND_LIMIT:
            raise ValueError("setup command is too long for Windows")
        return Invocation(args, log=windows_log_path(name))

    helper_args = [mode, "--tries", str(tries), "--hosts", " ".join(hosts)]
    for s in strategies:
        helper_args += ["--strategy", s]
    if dns_dot:
        helper_args.append("--dns-dot")
    cmd = ["/bin/bash", "-c", LINUX_BOOTSTRAP, "dpi-dashboard-bootstrap", *helper_args]
    if elevate == "auto" and os.geteuid() != 0:
        cmd = ["pkexec", *cmd]
    elif elevate == "sudo":
        cmd = ["sudo", *cmd]
    return Invocation(cmd, stdin=helper_text("setup-linux.sh").encode("utf-8"))


def run(inv: Invocation, on_line: Callable[[str], None], poll: float = 0.3) -> int:
    """Run the helper, calling on_line for every line of progress. Blocks until it ends."""
    if inv.log is None:
        p = subprocess.Popen(inv.args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, creationflags=_NO_WINDOW)
        assert p.stdin and p.stdout
        p.stdin.write(inv.stdin or b"")
        p.stdin.close()
        for raw in p.stdout:
            on_line(raw.decode("utf-8", "replace").rstrip("\r\n"))
        return p.wait()

    tail = LogTail(inv.log)
    p = subprocess.Popen(inv.args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    while p.poll() is None:
        for line in tail.read():
            on_line(line)
        time.sleep(poll)
    for line in tail.read():
        on_line(line)
    if tail.buf:
        on_line(tail.buf)
    return p.returncode
