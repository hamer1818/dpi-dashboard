"""The config-editing functions of the Linux helper, run with bash on a copy."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HELPER = Path(__file__).parents[1] / "src/dpi_dashboard/assets/setup-linux.sh"
pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"),
                                reason="needs bash")

UPSTREAM_LIKE = """# comment
NFQWS_ENABLE=0
NFQWS_PORTS_TCP=80,443
NFQWS_PORTS_UDP=443
NFQWS_OPT="
--filter-tcp=80 --dpi-desync=fake <HOSTLIST> --new
--filter-udp=443 --dpi-desync=fake <HOSTLIST_NOAUTO>
"
MODE_FILTER=none
"""


def run(zdir, script):
    fns = subprocess.run(["sed", "-n", "/^set_conf()/,/^}/p; /^set_strategy()/,/^}/p",
                          str(HELPER)], capture_output=True, text=True, check=True).stdout
    subprocess.run(["bash", "-c", fns + "\n" + script], check=True,
                   env={**os.environ, "ZDIR": str(zdir)})
    return (zdir / "config").read_text()


def test_strategy_and_settings(tmp_path):
    (tmp_path / "config").write_text(UPSTREAM_LIKE)
    out = run(tmp_path, "set_conf NFQWS_ENABLE 1; set_conf NFQWS_PORTS_UDP ''; "
                        "set_strategy '--dpi-desync=multisplit --dpi-desync-split-pos=2'")
    assert "NFQWS_ENABLE=1\n" in out and "NFQWS_PORTS_UDP=\n" in out
    assert out.count("NFQWS_OPT=") == 1
    assert ('NFQWS_OPT="\n--filter-tcp=80 --hostcase <HOSTLIST> --new\n'
            '--filter-tcp=443 --dpi-desync=multisplit --dpi-desync-split-pos=2 <HOSTLIST>\n"\n'
            "MODE_FILTER=none\n") in out
    # zapret sources this file with sh: it must stay valid shell.
    subprocess.run(["sh", "-n", str(tmp_path / "config")], check=True)


def test_single_line_block_and_missing_keys(tmp_path):
    (tmp_path / "config").write_text('A=1\nNFQWS_OPT="--x"\nB=2\n')
    out = run(tmp_path, "set_strategy '--y'; set_conf NEW 5")
    assert out.startswith("A=1\nNFQWS_OPT=\"\n") and "B=2\n" in out and out.endswith("NEW=5\n")
    (tmp_path / "config").write_text("A=1\n")
    assert "--filter-tcp=443 --z <HOSTLIST>" in run(tmp_path, "set_strategy '--z'")


def test_refuses_without_root():
    if os.geteuid() == 0:
        pytest.skip("running as root")
    r = subprocess.run(["bash", str(HELPER), "tune"], capture_output=True, text=True)
    assert r.returncode == 1 and "@@ERROR must run as root" in r.stdout


# --- root-side download verification -----------------------------------------------------

def call(tmp_path, fn_names, command):
    """Run `command` with the named helper functions defined; return (ok, output)."""
    pattern = "; ".join(f"/^{n}()/,/^}}/p" for n in fn_names)
    fns = subprocess.run(["sed", "-n", pattern, str(HELPER)], capture_output=True, text=True,
                         check=True).stdout
    script = tmp_path / "t.sh"
    script.write_text(fns + "\n" + command + "\n")
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    return r.returncode == 0, r.stdout + r.stderr


def tarball(tmp_path, name, *members):
    import io
    import tarfile
    path = tmp_path / name
    with tarfile.open(path, "w:gz") as t:
        for info in members:
            t.addfile(info, io.BytesIO(b"x" * info.size))
    return path


def member(name, kind=None, link=""):
    import tarfile
    i = tarfile.TarInfo(name)
    i.size = 1 if kind is None else 0
    if kind:
        i.type, i.linkname = kind, link
    return i


def test_digest(tmp_path):
    import hashlib
    f = tmp_path / "a"
    f.write_bytes(b"zapret")
    good = hashlib.sha256(b"zapret").hexdigest()
    assert call(tmp_path, ["verify_digest"], f"verify_digest {f} {good}")[0]
    assert not call(tmp_path, ["verify_digest"], f"verify_digest {f} {'b' * 64}")[0]


@pytest.mark.parametrize("bad", [
    member("zapret-v1/../../etc/evil"),
    member("/etc/evil"),
    member("zapret-v1/link", __import__("tarfile").SYMTYPE, "../../../etc/shadow"),
    member("zapret-v1/link", __import__("tarfile").SYMTYPE, "/etc/shadow"),
    member("zapret-v1/hard", __import__("tarfile").LNKTYPE, "../etc/shadow"),
    member("zapret-v1/dev", __import__("tarfile").CHRTYPE),
])
def test_unsafe_archives_are_refused(tmp_path, bad):
    arc = tarball(tmp_path, "bad.tgz", member("zapret-v1/ok"), bad)
    assert not call(tmp_path, ["check_archive"], f"check_archive {arc}")[0]


def test_normal_archive_is_accepted(tmp_path):
    import tarfile
    arc = tarball(tmp_path, "ok.tgz", member("zapret-v1/bin/nfqws"),
                  member("zapret-v1/nfq/nfqws", tarfile.SYMTYPE, "../bin/nfqws"))
    ok, out = call(tmp_path, ["check_archive"], f"check_archive {arc}")
    assert ok, out


def release_json(tmp_path, **change):
    import json
    p = "https://github.com/bol-van/zapret/releases/download/v72.1/"
    d = {"tag_name": "v72.1", "assets": [
        {"name": "zapret-v72.1.tar.gz", "browser_download_url": p + "zapret-v72.1.tar.gz",
         "digest": "sha256:" + "a" * 64},
        {"name": "sha256sum.txt", "browser_download_url": p + "sha256sum.txt"}]}
    if "tag" in change:
        d["tag_name"] = change["tag"]
    if "url" in change:
        d["assets"][0]["browser_download_url"] = change["url"]
    if change.get("no_digest"):
        del d["assets"][0]["digest"]
    f = tmp_path / "release.json"
    f.write_text(json.dumps(d))
    return f


def test_release_info(tmp_path):
    ok, out = call(tmp_path, ["read_release"], f"read_release {release_json(tmp_path)}")
    assert ok and out.split() == ["v72.1", "https://github.com/bol-van/zapret/releases/download/"
                                  "v72.1/zapret-v72.1.tar.gz", "a" * 64,
                                  "https://github.com/bol-van/zapret/releases/download/"
                                  "v72.1/sha256sum.txt"]


@pytest.mark.parametrize("change, reason", [
    ({"url": "https://evil.example/zapret-v72.1.tar.gz"}, "unexpected download URL"),
    ({"no_digest": True}, "did not publish a checksum"),
    ({"tag": "v1;reboot"}, "unexpected tag"),
])
def test_release_info_is_validated(tmp_path, change, reason):
    ok, out = call(tmp_path, ["read_release"], f"read_release {release_json(tmp_path, **change)}")
    assert not ok and reason in out
