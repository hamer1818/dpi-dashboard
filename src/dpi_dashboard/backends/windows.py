"""Windows backend: a Windows service (zapret/winws, GoodbyeDPI), elevated through UAC."""

from __future__ import annotations

import base64
import re

from .base import Backend, Runner, ServiceState, ToggleResult, default_runner

# Service names used by the common installers:
#   zapret-discord-youtube "service.bat" -> "zapret"
#   GoodbyeDPI "service_install_*.cmd"   -> "GoodbyeDPI"
_VALID_NAME = re.compile(r"^[A-Za-z0-9_.\-]{1,256}$")
_ERROR_SERVICE_DOES_NOT_EXIST = 1060
_ERROR_CANCELLED = 1223          # UAC prompt dismissed
_SERVICE_RUNNING = 4
_SERVICE_AUTO_START = 2


def _encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


class WindowsServiceBackend(Backend):
    kind = "windows-service"
    DEFAULT_SERVICES = ("zapret", "GoodbyeDPI")

    def __init__(self, service: str, runner: Runner = default_runner):
        # The name ends up inside a PowerShell command line.
        if not _VALID_NAME.match(service):
            raise ValueError(f"invalid service name: {service!r}")
        super().__init__(service, runner)

    def state(self) -> ServiceState:
        # sc.exe labels can be localized, the numeric codes are not.
        q = self.run(["sc", "query", self.service])
        if q.returncode == _ERROR_SERVICE_DOES_NOT_EXIST or "1060" in q.stdout:
            return ServiceState(installed=False)
        m = re.search(r"STATE\s*:\s*(\d+)", q.stdout)
        if q.returncode != 0 or not m:
            return ServiceState(installed=False)
        qc = self.run(["sc", "qc", self.service])
        s = re.search(r"START_TYPE\s*:\s*(\d+)", qc.stdout)
        return ServiceState(
            installed=True,
            active=int(m.group(1)) == _SERVICE_RUNNING,
            enabled=bool(s) and int(s.group(1)) == _SERVICE_AUTO_START,
        )

    def elevated_script(self, on: bool) -> str:
        n = self.service
        body = (f"Set-Service -Name '{n}' -StartupType Automatic; Start-Service -Name '{n}'"
                if on else
                f"Stop-Service -Name '{n}' -Force; Set-Service -Name '{n}' -StartupType Manual")
        return "$ErrorActionPreference = 'Stop'; " + body

    def toggle_command(self, on: bool) -> list[str]:
        inner = _encode(self.elevated_script(on))
        outer = (
            "try { $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
            f"-ArgumentList '-NoProfile','-NonInteractive','-EncodedCommand','{inner}'; "
            f"exit $p.ExitCode }} catch {{ exit {_ERROR_CANCELLED} }}"
        )
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", outer]

    def set_enabled(self, on: bool) -> ToggleResult:
        r = self.run(self.toggle_command(on), timeout=None)
        if r.returncode == 0:
            return ToggleResult(True)
        if r.returncode == _ERROR_CANCELLED:
            return ToggleResult(False, cancelled=True)
        return ToggleResult(False, message=(r.stderr or r.stdout).strip()
                            or f"exit code {r.returncode}")
