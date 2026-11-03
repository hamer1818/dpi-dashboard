import hashlib
import io
import json

import pytest

from dpi_dashboard import updater

EXE = b"new program"
EXE_SHA = hashlib.sha256(EXE).hexdigest()
PREFIX = updater.DOWNLOAD_PREFIX + "v9.0.0/"


def release_json(tag="v9.0.0", digest=f"sha256:{EXE_SHA}", url=None):
    name = f"dpi-dashboard-{tag}-windows-x64.exe"
    return {"tag_name": tag, "html_url": "https://github.com/x/releases/tag/" + tag,
            "assets": [{"name": name, "browser_download_url": url or PREFIX + name,
                        "digest": digest},
                       {"name": "SHA256SUMS", "browser_download_url": PREFIX + "SHA256SUMS",
                        "digest": None}]}


def opener(files):
    def open_(req, timeout=None):
        body = files[req.full_url]
        return io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode())
    return open_


def files(sums_name="dpi-dashboard-v9.0.0-windows-x64.exe", sha=EXE_SHA, rel=None):
    return {updater.API: rel or release_json(),
            PREFIX + "SHA256SUMS": f"{sha}  {sums_name}\n".encode(),
            PREFIX + "dpi-dashboard-v9.0.0-windows-x64.exe": EXE}


def test_versions():
    assert updater.parse_version("v0.4.10") > updater.parse_version("0.4.9")
    assert updater.parse_version("1.0") is None


def test_up_to_date_and_newer():
    f = files()
    assert updater.check("9.0.0", "exe", opener(f)) is None
    rel = updater.check("0.4.1", "exe", opener(f))
    assert rel.version == "9.0.0" and rel.asset.digest == EXE_SHA
    assert updater.check("0.4.1", None, opener(f)).asset is None      # notice only


def test_download_is_verified(tmp_path):
    f = files()
    rel = updater.check("0.4.1", "exe", opener(f))
    out = updater.download(rel, tmp_path / "new.exe", opener(f))
    assert out.read_bytes() == EXE

    f[PREFIX + "dpi-dashboard-v9.0.0-windows-x64.exe"] = b"tampered"
    with pytest.raises(updater.UpdateError, match="checksum"):
        updater.download(rel, tmp_path / "bad.exe", opener(f))
    assert not (tmp_path / "bad.exe").exists() and not list(tmp_path.glob("*.part"))


def test_checksums_must_agree(tmp_path):
    f = files(sha="0" * 64)
    rel = updater.check("0.4.1", "exe", opener(f))
    with pytest.raises(updater.UpdateError, match="disagree"):
        updater.download(rel, tmp_path / "x.exe", opener(f))
    f = files(sums_name="something-else.exe")
    with pytest.raises(updater.UpdateError, match="does not list"):
        updater.download(updater.check("0.4.1", "exe", opener(f)), tmp_path / "x.exe", opener(f))


def test_foreign_download_urls_are_refused():
    f = files(rel=release_json(url="https://evil.example/dpi-dashboard.exe"))
    with pytest.raises(updater.UpdateError, match="URL"):
        updater.check("0.4.1", "exe", opener(f))


def test_unexpected_tag_is_refused():
    with pytest.raises(updater.UpdateError):
        updater.check("0.4.1", "exe", opener(files(rel=release_json(tag="latest"))))


def test_exe_swap_keeps_the_name(tmp_path):
    exe, new = tmp_path / "DPI Dashboard.exe", tmp_path / ".dpi-dashboard-update.exe"
    exe.write_bytes(b"old")
    new.write_bytes(b"new")
    updater.apply_exe(new, exe)
    assert exe.read_bytes() == b"new" and updater.old_exe(exe).read_bytes() == b"old"
    assert not new.exists()


def test_asset_names():
    assert updater.asset_name("exe", "v1.2.3") == "dpi-dashboard-v1.2.3-windows-x64.exe"
    assert updater.asset_name("venv", "v1.2.3") == "dpi_dashboard-1.2.3-py3-none-any.whl"
    assert updater.asset_name(None, "v1.2.3") is None
