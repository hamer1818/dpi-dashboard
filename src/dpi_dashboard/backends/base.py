"""Common types for service backends."""

from __future__ import annotations

import subprocess
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

# Hide the console window that would otherwise flash on Windows for every call.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

Runner = Callable[..., subprocess.CompletedProcess]


def default_runner(args: list[str], timeout: float | None = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )


@dataclass(frozen=True)
class ServiceState:
    installed: bool
    active: bool = False
    enabled: bool = False


@dataclass(frozen=True)
class ToggleResult:
    ok: bool
    cancelled: bool = False
    message: str = ""


class Backend(ABC):
    """Controls one system service that performs the actual DPI bypass."""

    kind: str = ""
    DEFAULT_SERVICES: tuple[str, ...] = ()

    def __init__(self, service: str, runner: Runner = default_runner):
        self.service = service
        self.run = runner

    @property
    def label(self) -> str:
        return f"{self.kind}: {self.service}"

    @classmethod
    def available(cls) -> bool:
        """Whether this kind of backend can work on the current machine."""
        return True

    @abstractmethod
    def state(self) -> ServiceState:
        """Current state. Must not need elevated rights."""

    @abstractmethod
    def set_enabled(self, on: bool) -> ToggleResult:
        """Start and enable at boot (on) or stop and disable (off).

        Asks for administrator rights and blocks until the user answers.
        """
