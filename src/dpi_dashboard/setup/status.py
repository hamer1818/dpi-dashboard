"""What is installed, what is missing, and whether DNS answers look forged."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..backends import detect_backend

LINUX_DIR = Path("/opt/zapret")
MARKER = ".installed-by-dpi-dashboard"
DOH_ENDPOINTS = ("https://cloudflare-dns.com/dns-query?name={}&type=A",
                 "https://dns.google/resolve?name={}&type=A")


def windows_dir() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "zapret"


@dataclass
class DnsCheck:
    host: str
    state: str = "unknown"            # "ok", "mismatch" or "unknown"
    system: list[str] = field(default_factory=list)
    encrypted: list[str] = field(default_factory=list)
    error: str = ""                   # why the check could not be made


@dataclass
class SetupStatus:
    platform: str                     # "linux", "windows" or "other"
    service: str | None = None        # name of the service that was found or looked for
    service_found: bool = False
    files_present: bool = False
    managed: bool = False             # installed by DPI Dashboard (can be removed by it)
    missing_required: list[str] = field(default_factory=list)  # setup cannot work
    missing_auto: list[str] = field(default_factory=list)      # setup installs these
    resolved_active: bool = False     # systemd-resolved in use (Linux DNS-over-TLS option)
    dot_active: bool = False          # ...and already sending DNS over TLS
    dns: DnsCheck | None = None

    @property
    def can_install(self) -> bool:
        return not self.missing_required and not self.files_present and not self.service_found

    @property
    def can_tune(self) -> bool:
        if self.missing_required or not self.service_found:
            return False
        # On Windows only our own service is retuned: rewriting another installer's
        # command line would break its own setup (lists, multiple instances).
        return (self.platform == "linux" and self.files_present) or self.managed


def system_addresses(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return []
    return sorted({i[4][0] for i in infos})


def _encrypted(host: str, opener=urlopen, timeout: float = 6) -> tuple[list[str], str]:
    errors = []
    for url in DOH_ENDPOINTS:
        try:
            req = Request(url.format(quote(host)), headers={"Accept": "application/dns-json"})
            with opener(req, timeout=timeout) as r:
                data = json.load(r)
            return sorted({a["data"] for a in data.get("Answer", []) if a.get("type") == 1}), ""
        except (OSError, ValueError, KeyError) as e:
            errors.append(f"{url.split('/')[2]}: {getattr(e, 'reason', None) or e}")
    return [], "; ".join(errors)


def encrypted_addresses(host: str, opener=urlopen, timeout: float = 6) -> list[str]:
    return _encrypted(host, opener, timeout)[0]


def check_dns(host: str, opener=urlopen) -> DnsCheck:
    """Compare the system resolver with DNS over HTTPS.

    Providers that block by DNS answer with a different address. No overlap is reported
    as a mismatch; it is a strong hint, not proof (some CDNs answer differently by region).
    """
    encrypted, err = _encrypted(host, opener)
    d = DnsCheck(host, system=system_addresses(host), encrypted=encrypted)
    if d.system and d.encrypted:
        d.state = "ok" if set(d.system) & set(d.encrypted) else "mismatch"
    elif not d.system:
        d.error = "system resolver returned no address"
    else:
        d.error = f"DNS over HTTPS unreachable ({err})" if err else "DNS over HTTPS gave no address"
    return d


def _linux(st: SetupStatus) -> None:
    if not os.path.isdir("/run/systemd/system"):
        st.missing_required.append("systemd")
    if shutil.which("pkexec") is None and os.geteuid() != 0:
        st.missing_required.append("pkexec (polkit)")
    if shutil.which("curl") is None:
        st.missing_auto.append("curl")
    if shutil.which("nft") is None and shutil.which("iptables") is None:
        st.missing_auto.append("nftables")
    st.files_present = (LINUX_DIR / "init.d" / "sysv" / "zapret").exists()
    st.managed = (LINUX_DIR / MARKER).exists()
    resolv = Path("/etc/resolv.conf")
    stub = resolv.exists() and "127.0.0.53" in resolv.read_text(errors="replace")
    st.resolved_active = os.path.isdir("/run/systemd/resolve") and stub
    if st.resolved_active and shutil.which("resolvectl"):
        try:
            out = subprocess.run(["resolvectl", "status"], capture_output=True, text=True,
                                 timeout=5).stdout
            st.dot_active = "+DNSOverTLS" in out
        except (OSError, subprocess.TimeoutExpired):
            pass


def _windows(st: SetupStatus) -> None:
    import platform
    if platform.machine().lower() not in ("amd64", "x86_64"):
        st.missing_required.append("64-bit Windows (x64)")
    d = windows_dir()
    st.files_present = (d / "winws.exe").exists()
    st.managed = (d / MARKER).exists()


def check(service: str | None = None, dns_host: str | None = "discord.com") -> SetupStatus:
    plat = "windows" if sys.platform == "win32" else "linux" if sys.platform.startswith("linux") \
        else "other"
    st = SetupStatus(plat)
    if plat == "linux":
        _linux(st)
    elif plat == "windows":
        _windows(st)
    else:
        st.missing_required.append("Linux or Windows")
    try:
        b = detect_backend("auto", service)
    except ValueError:
        b = None
    if b is not None:
        st.service = b.service
        st.service_found = b.state().installed
    if dns_host:
        st.dns = check_dns(dns_host)
    return st
