"""Linux backend: a systemd system unit, elevated with pkexec (polkit)."""

from __future__ import annotations

import os
import shutil

from .base import Backend, ServiceState, ToggleResult

# pkexec exit codes: 126 = the user dismissed the dialog, 127 = not authorized.
_PKEXEC_DENIED = (126, 127)


class SystemdBackend(Backend):
    kind = "systemd"
    # zapret's install_easy.sh and the Arch/AUR packages both install "zapret.service".
    DEFAULT_SERVICES = ("zapret.service",)

    @classmethod
    def available(cls) -> bool:
        return shutil.which("systemctl") is not None and os.path.isdir("/run/systemd/system")

    def state(self) -> ServiceState:
        r = self.run(["systemctl", "show", self.service,
                      "--property=LoadState,ActiveState,UnitFileState"])
        props = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        if r.returncode != 0 or props.get("LoadState", "not-found") == "not-found":
            return ServiceState(installed=False)
        return ServiceState(
            installed=True,
            active=props.get("ActiveState") == "active",
            enabled=props.get("UnitFileState", "").startswith("enabled"),
        )

    def toggle_command(self, on: bool) -> list[str]:
        systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
        return ["pkexec", systemctl, "enable" if on else "disable", "--now", self.service]

    def set_enabled(self, on: bool) -> ToggleResult:
        if shutil.which("pkexec") is None:
            return ToggleResult(False, message="pkexec not found (install polkit)")
        r = self.run(self.toggle_command(on), timeout=None)
        if r.returncode == 0:
            return ToggleResult(True)
        if r.returncode in _PKEXEC_DENIED:
            return ToggleResult(False, cancelled=True)
        return ToggleResult(False, message=(r.stderr or r.stdout).strip())
