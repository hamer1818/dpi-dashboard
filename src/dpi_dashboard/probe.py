"""Connectivity test: can we complete a TLS handshake and get an HTTP answer?

DPI blocking usually shows up as a connection reset in the middle of the TLS
handshake, right after the server name (SNI) is sent. Anything that returns an HTTP
status line, including 3xx and 4xx, counts as reachable.
"""

from __future__ import annotations

import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

# Why a single attempt failed.
RESET, TIMEOUT, DNS, CERT, TLS, NO_HTTP, ERROR = (
    "reset", "timeout", "dns", "cert", "tls", "no-http", "error")


@dataclass(frozen=True)
class Attempt:
    ok: bool
    reason: str = ""


@dataclass
class HostResult:
    host: str
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def successes(self) -> int:
        return sum(a.ok for a in self.attempts)

    @property
    def reasons(self) -> list[str]:
        return sorted({a.reason for a in self.attempts if not a.ok})


def check_host(host: str, port: int = 443, timeout: float = 6.0,
               context: ssl.SSLContext | None = None) -> Attempt:
    ctx = context or ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with ctx.wrap_socket(raw, server_hostname=host) as tls:
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\n"
                            "User-Agent: dpi-dashboard\r\nConnection: close\r\n\r\n".encode())
                head = tls.recv(16)
        return Attempt(True) if head.startswith(b"HTTP/") else Attempt(False, NO_HTTP)
    except socket.gaierror:
        return Attempt(False, DNS)
    except ssl.SSLCertVerificationError:
        return Attempt(False, CERT)
    except (ConnectionResetError, ConnectionAbortedError, ssl.SSLEOFError,
            ssl.SSLZeroReturnError):
        return Attempt(False, RESET)
    except TimeoutError:
        return Attempt(False, TIMEOUT)
    except ssl.SSLError:
        return Attempt(False, TLS)
    except OSError:
        return Attempt(False, ERROR)


def check_hosts(hosts: list[str], tries: int = 3, timeout: float = 6.0) -> list[HostResult]:
    """Try every host `tries` times, hosts in parallel."""
    def one(host: str) -> HostResult:
        return HostResult(host, [check_host(host, timeout=timeout) for _ in range(tries)])
    if not hosts:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(hosts))) as ex:
        return list(ex.map(one, hosts))
