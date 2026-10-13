"""Pick the right backend for this machine."""

from __future__ import annotations

import sys

from .base import Backend, ServiceState, ToggleResult
from .systemd import SystemdBackend
from .windows import WindowsServiceBackend

KINDS: dict[str, type[Backend]] = {
    SystemdBackend.kind: SystemdBackend,
    WindowsServiceBackend.kind: WindowsServiceBackend,
}

__all__ = ["Backend", "ServiceState", "ToggleResult", "SystemdBackend",
           "WindowsServiceBackend", "KINDS", "detect_backend"]


def detect_backend(kind: str = "auto", service: str | None = None) -> Backend | None:
    """Return a backend for the first installed candidate service.

    If none of the candidates is installed, the backend for the first one is returned
    anyway so the UI can say which service it looked for. Returns None only when no
    backend kind works on this platform.
    """
    if kind == "auto":
        if sys.platform == "win32":
            cls: type[Backend] | None = WindowsServiceBackend
        elif SystemdBackend.available():
            cls = SystemdBackend
        else:
            cls = None
    else:
        cls = KINDS.get(kind)
    if cls is None:
        return None
    names = [service] if service else list(cls.DEFAULT_SERVICES)
    backends = [cls(n) for n in names]
    for b in backends:
        if b.state().installed:
            return b
    return backends[0]
