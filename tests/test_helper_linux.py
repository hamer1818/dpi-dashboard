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


def test_refuses_without_root(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("running as root")
    log = tmp_path / "log"
    r = subprocess.run(["bash", str(HELPER), "tune", str(log)], capture_output=True, text=True)
    assert r.returncode == 1 and "@@ERROR must run as root" in log.read_text()
