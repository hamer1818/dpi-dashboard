import hashlib
import io
import json
import tarfile

import pytest

from dpi_dashboard.setup import upstream

VERSION = "v99.1"
FILES = {
    "install_bin.sh": b"#!/bin/sh\necho ok\n",
    "config.default": b"NFQWS_ENABLE=0\n",
    "binaries/linux-x86_64/nfqws": b"\x7fELF fake nfqws",
}


def make_tar(files, extra=None):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(f"zapret-{VERSION}/{name}")
            info.size, info.mode = len(data), 0o755
            t.addfile(info, io.BytesIO(data))
        for info, data in (extra or []):
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def sums_for(files, tamper=None):
    lines = []
    for name, data in files.items():
        digest = hashlib.sha256(data).hexdigest()
        if name == tamper:
            digest = "0" * 64
        lines.append(f"{digest}  zapret-{VERSION}/binaries/linux-x86_64/nfqws"
                     if name.startswith("binaries") else None)
    return "\n".join(x for x in lines if x) + "\n"


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_for(archive, sums, digest=None):
    name = f"zapret-{VERSION}.tar.gz"
    api = {"tag_name": VERSION, "assets": [
        {"name": name, "browser_download_url": "https://x/archive",
         "digest": digest if digest is not None else
         "sha256:" + hashlib.sha256(archive).hexdigest()},
        {"name": "sha256sum.txt", "browser_download_url": "https://x/sums"}]}
    routes = {upstream.API_LATEST: json.dumps(api).encode(), "https://x/archive": archive,
              "https://x/sums": sums.encode()}
    return lambda req, timeout=None: FakeResponse(routes[req.full_url])


def test_prepare_verifies_and_extracts(tmp_path):
    archive = make_tar(FILES)
    rel, root = upstream.prepare(tmp_path, "tar.gz",
                                 opener=opener_for(archive, sums_for(FILES)))
    assert rel.version == VERSION and root.name == f"zapret-{VERSION}"
    nfqws = "binaries/linux-x86_64/nfqws"
    assert (root / nfqws).read_bytes() == FILES[nfqws]
    assert (root / "install_bin.sh").stat().st_mode & 0o100


def test_archive_checksum_mismatch(tmp_path):
    archive = make_tar(FILES)
    with pytest.raises(upstream.SetupError, match="checksum"):
        upstream.prepare(tmp_path, "tar.gz",
                         opener=opener_for(archive, sums_for(FILES), "sha256:" + "0" * 64))


def test_missing_digest_is_refused(tmp_path):
    archive = make_tar(FILES)
    with pytest.raises(upstream.SetupError, match="checksum"):
        upstream.prepare(tmp_path, "tar.gz", opener=opener_for(archive, sums_for(FILES), ""))


def test_tampered_program_is_refused(tmp_path):
    archive = make_tar(FILES)
    bad = sums_for(FILES, tamper="binaries/linux-x86_64/nfqws")
    with pytest.raises(upstream.SetupError, match="checksum mismatch"):
        upstream.prepare(tmp_path, "tar.gz", opener=opener_for(archive, bad))


def test_path_traversal_is_refused(tmp_path):
    evil = tarfile.TarInfo("../../etc/evil")
    evil.size = 1
    archive = make_tar(FILES, extra=[(evil, b"x")])
    with pytest.raises(upstream.SetupError, match="unsafe path"):
        upstream.prepare(tmp_path, "tar.gz", opener=opener_for(archive, sums_for(FILES)))
    assert not (tmp_path.parent.parent / "etc" / "evil").exists()


def test_symlink_out_of_tree_is_refused(tmp_path):
    link = tarfile.TarInfo(f"zapret-{VERSION}/link")
    link.type, link.linkname = tarfile.SYMTYPE, "../../../../etc/passwd"
    archive = make_tar(FILES, extra=[(link, b"")])
    with pytest.raises(upstream.SetupError, match="unsafe path"):
        upstream.prepare(tmp_path, "tar.gz", opener=opener_for(archive, sums_for(FILES)))
