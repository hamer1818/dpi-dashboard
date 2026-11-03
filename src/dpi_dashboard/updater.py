"""Updates from the GitHub releases of DPI Dashboard.

The app checks the latest release. Where it can replace itself, it downloads the new
build next to the running one, checks it against the release's SHA256SUMS and the
SHA-256 digest GitHub publishes for the file, and swaps it in when the app restarts or
quits:

- Windows program (.exe): the running file is renamed to *.old.exe (Windows allows
  renaming a running program, not deleting it) and the new one takes its name, so
  shortcuts and the autostart entry keep working. The old file is deleted on the next
  start.
- Linux user install (scripts/install-linux.sh): the release wheel is installed into the
  app's own virtual environment with pip.

Anything else (a distribution package, running from source) only gets a notice with a
link to the release page.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from . import __version__

API = "https://api.github.com/repos/hamer1818/dpi-dashboard/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/hamer1818/dpi-dashboard/releases/download/"
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    digest: str           # sha256 hex from GitHub, "" if it published none


@dataclass(frozen=True)
class Release:
    tag: str
    version: str
    page: str             # release page, for the notice
    asset: Asset | None   # the file this install can update itself with
    sums: Asset | None    # SHA256SUMS


def parse_version(s: str) -> tuple[int, ...] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", s.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def user_venv() -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data / "dpi-dashboard" / "venv"


def install_kind() -> str | None:
    """"exe" (Windows program), "venv" (Linux user install) or None (cannot self-update)."""
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return "exe"
    if sys.platform.startswith("linux") and Path(sys.prefix).resolve() == user_venv().resolve():
        return "venv"
    return None


def asset_name(kind: str | None, tag: str) -> str | None:
    if kind == "exe":
        return f"dpi-dashboard-{tag}-windows-x64.exe"
    if kind == "venv":
        return f"dpi_dashboard-{tag[1:]}-py3-none-any.whl"
    return None


def _get(url: str, opener, timeout: float):
    req = Request(url, headers={"User-Agent": f"dpi-dashboard/{__version__}",
                                "Accept": "application/vnd.github+json"})
    return opener(req, timeout=timeout)


def _asset(data: dict, name: str | None) -> Asset | None:
    for a in data.get("assets", []):
        if name and a.get("name") == name:
            url = str(a.get("browser_download_url", ""))
            if not url.startswith(DOWNLOAD_PREFIX):
                raise UpdateError(f"unexpected download URL: {url}")
            digest = str(a.get("digest") or "")
            return Asset(name, url, digest[7:] if digest.startswith("sha256:") else "")
    return None


def check(current: str = __version__, kind: str | None = None, opener=urlopen,
          timeout: float = 15) -> Release | None:
    """The latest release if it is newer than `current`, else None."""
    with _get(API, opener, timeout) as r:
        data = json.load(r)
    tag = str(data.get("tag_name", ""))
    if not TAG.match(tag):
        raise UpdateError(f"unexpected release tag: {tag!r}")
    new, cur = parse_version(tag), parse_version(current)
    if cur is not None and new <= cur:
        return None
    return Release(tag, tag[1:], str(data.get("html_url") or ""),
                   _asset(data, asset_name(kind, tag)), _asset(data, "SHA256SUMS"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(rel: Release, dest: Path, opener=urlopen, timeout: float = 60) -> Path:
    """Download the release file to `dest` and verify it; returns `dest`."""
    if rel.asset is None or rel.sums is None:
        raise UpdateError("the release has no file for this install")
    with _get(rel.sums.url, opener, timeout) as r:
        sums = r.read(65536).decode("utf-8", "replace")
    want = ""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == rel.asset.name:
            want = parts[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", want):
        raise UpdateError(f"SHA256SUMS does not list {rel.asset.name}")
    if rel.asset.digest and rel.asset.digest.lower() != want:
        raise UpdateError("SHA256SUMS and GitHub's checksum disagree")

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    try:
        with _get(rel.asset.url, opener, timeout) as r, open(part, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        if _sha256(part) != want:
            raise UpdateError(f"{rel.asset.name} does not match its checksum")
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)
    return dest


def download_path(kind: str, rel: Release) -> Path:
    if kind == "exe":    # same folder as the program, so the swap is a rename
        return Path(sys.executable).with_name(".dpi-dashboard-update.exe")
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "dpi-dashboard" / rel.asset.name


def old_exe(exe: Path) -> Path:
    return exe.with_name(exe.stem + ".old" + exe.suffix)


def apply_exe(new: Path, exe: Path) -> None:
    old = old_exe(exe)
    old.unlink(missing_ok=True)
    os.replace(exe, old)
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)
        raise


def apply(kind: str, new: Path) -> None:
    """Put the downloaded update in place; the running program keeps working until exit."""
    try:
        if kind == "exe":
            apply_exe(new, Path(sys.executable))
        else:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                            "--disable-pip-version-check", str(new)],
                           check=True, capture_output=True, text=True, timeout=300)
            new.unlink(missing_ok=True)
    except subprocess.CalledProcessError as e:
        raise UpdateError((e.stderr or e.stdout or str(e)).strip()) from e
    except (OSError, subprocess.TimeoutExpired) as e:
        raise UpdateError(str(e)) from e


def cleanup() -> None:
    """Remove what an earlier update left behind (the replaced .exe)."""
    if install_kind() == "exe":
        exe = Path(sys.executable)
        for p in (old_exe(exe), exe.with_name(".dpi-dashboard-update.exe")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass          # the old program is still closing; next start
