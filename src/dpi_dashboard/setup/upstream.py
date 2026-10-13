"""Download and verify a zapret release from github.com/bol-van/zapret."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = "bol-van/zapret"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "dpi-dashboard"

Progress = Callable[[int, int], None]


class SetupError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    version: str
    archive_name: str
    archive_url: str
    archive_digest: str      # "sha256:<hex>" from the GitHub API
    sums_url: str            # upstream sha256sum.txt (hashes of the files inside)


def _get(url: str, timeout: float = 30, opener=urlopen):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    # Unauthenticated API calls are limited to 60 per hour per IP address, which shared
    # addresses (CI machines, mobile carriers) can exhaust. A token lifts that limit.
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return opener(Request(url, headers=headers), timeout=timeout)


def latest_release(archive: str, opener=urlopen) -> Release:
    """archive: "tar.gz" (Linux) or "zip" (Windows)."""
    try:
        with _get(API_LATEST, opener=opener) as r:
            data = json.load(r)
    except HTTPError as e:
        if e.code in (403, 429):
            raise SetupError("GitHub's request limit was reached for this network; "
                             "try again in an hour (or set GITHUB_TOKEN)") from e
        raise SetupError(f"GitHub API: HTTP {e.code}") from e
    tag = data["tag_name"]
    assets = {a["name"]: a for a in data.get("assets", [])}
    name = f"zapret-{tag}.{archive}"
    if name not in assets or "sha256sum.txt" not in assets:
        raise SetupError(f"release {tag} has no {name} or sha256sum.txt")
    digest = assets[name].get("digest") or ""
    if not digest.startswith("sha256:"):
        raise SetupError(f"GitHub did not provide a checksum for {name}")
    return Release(tag, name, assets[name]["browser_download_url"], digest,
                   assets["sha256sum.txt"]["browser_download_url"])


def download(url: str, dest: Path, progress: Progress | None = None, opener=urlopen) -> Path:
    with _get(url, timeout=60, opener=opener) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_digest(path: Path, digest: str) -> None:
    algo, _, expected = digest.partition(":")
    if algo != "sha256" or sha256(path) != expected.lower():
        raise SetupError(f"checksum mismatch for {path.name}")


def _check_member(name: str) -> None:
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts:
        raise SetupError(f"unsafe path in archive: {name}")


def extract(archive: Path, dest: Path) -> Path:
    """Extract safely and return the single top-level directory."""
    dest.mkdir(parents=True, exist_ok=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                _check_member(n)
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                _check_member(m.name)
                if m.issym() or m.islnk():
                    _check_member(str(PurePosixPath(m.name).parent / m.linkname))
            if hasattr(tarfile, "data_filter"):
                t.extractall(dest, filter="data")
            else:  # Python < 3.10.12 / 3.11.4; members were checked above
                t.extractall(dest)  # noqa: S202
    tops = [p for p in dest.iterdir() if p.is_dir()]
    if len(tops) != 1:
        raise SetupError("unexpected archive layout")
    return tops[0]


def verify_files(root: Path, sums: str) -> int:
    """Check every file listed in upstream's sha256sum.txt. Returns how many were checked."""
    checked = 0
    for line in sums.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        expected, rel = parts[0].lower(), parts[1].strip().lstrip("*")
        _check_member(rel)
        rel_parts = PurePosixPath(rel).parts
        path = root.parent.joinpath(*rel_parts)
        if not path.is_file():
            raise SetupError(f"missing file from release: {rel}")
        if sha256(path) != expected:
            raise SetupError(f"checksum mismatch: {rel}")
        checked += 1
    if checked == 0:
        raise SetupError("sha256sum.txt lists no files")
    return checked


def prepare(workdir: Path, archive: str, log: Callable[[str], None] = lambda s: None,
            progress: Progress | None = None, opener=urlopen) -> tuple[Release, Path]:
    """Download, verify and extract the latest release into workdir."""
    rel = latest_release(archive, opener=opener)
    log(f"release {rel.version}: {rel.archive_url}")
    path = download(rel.archive_url, workdir / rel.archive_name, progress, opener=opener)
    verify_digest(path, rel.archive_digest)
    log(f"archive checksum OK ({rel.archive_digest})")
    sums = download(rel.sums_url, workdir / "sha256sum.txt", opener=opener).read_text()
    out = workdir / "src"
    if out.exists():
        shutil.rmtree(out)
    root = extract(path, out)
    n = verify_files(root, sums)
    log(f"{n} program files match upstream sha256sum.txt")
    return rel, root
