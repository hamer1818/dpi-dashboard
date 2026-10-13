import base64
import gzip
import os
import re
import subprocess
import sys

import pytest

from dpi_dashboard.setup import runner

STRATS = ["--dpi-desync=multisplit", "--dpi-desync=fake"]


def test_parse_protocol_lines():
    assert runner.parse_line("@@TRY 2 14/15\n") == runner.Event("try", ("2", "14/15"))
    assert runner.parse_line("@@DONE ok") == runner.Event("done", ("ok",))
    assert runner.parse_line("@@STEP verified v72.13") == \
        runner.Event("step", ("verified", "v72.13"))
    assert runner.parse_line("﻿@@STEP copy\r\n") == runner.Event("step", ("copy",))
    assert runner.parse_line("plain text").kind == "text"


def test_log_tail_returns_only_complete_new_lines(tmp_path):
    p = tmp_path / "log"
    p.write_text("a\nb")
    t = runner.LogTail(p)
    assert t.read() == ["a"]
    with open(p, "a") as f:
        f.write("c\nd\n")
    assert t.read() == ["bc", "d"]
    assert t.read() == []


def test_unsafe_strategies_never_reach_the_helper():
    assert runner.valid_strategies(["--dpi-desync=fake", "--x=$(reboot)", 'bad"']) == \
        ["--dpi-desync=fake"]
    with pytest.raises(ValueError):
        runner.valid_strategies(["rm -rf /"])


@pytest.mark.skipif(sys.platform == "win32", reason="Linux command")
def test_linux_helper_comes_from_memory_not_disk(monkeypatch):
    monkeypatch.setattr(runner.os, "geteuid", lambda: 1000)
    inv = runner.build("install", strategies=STRATS, hosts=["a.com", "b.com"], tries=2,
                       dns_dot=True)
    assert inv.args[:4] == ["pkexec", "/bin/bash", "-c", runner.LINUX_BOOTSTRAP]
    assert inv.stdin == runner.helper_text("setup-linux.sh").encode()
    assert inv.log is None
    assert not any(a.endswith((".sh", ".txt", ".log")) for a in inv.args)   # no files
    rest = inv.args[5:]
    assert rest[:5] == ["install", "--tries", "2", "--hosts", "a.com b.com"]
    assert rest.count("--strategy") == 2 and "--dns-dot" in rest
    assert runner.build("tune", strategies=STRATS, elevate="none").args[0] == "/bin/bash"


@pytest.mark.skipif(sys.platform == "win32", reason="needs bash")
def test_linux_bootstrap_runs_the_piped_script():
    """The real bootstrap: the script arrives on stdin, its arguments on the command line."""
    inv = runner.Invocation(["/bin/bash", "-c", runner.LINUX_BOOTSTRAP, "x", "one", "two words"],
                            stdin=b'echo "args:$#:$1:$2"; read -r line; echo "stdin:[$line]"\n')
    lines = []
    assert runner.run(inv, lines.append) == 0
    assert lines == ["args:2:one:two words", "stdin:[]"]   # the script cannot read stdin


def windows_inner(monkeypatch, mode, **kw):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    inv = runner.build(mode, strategies=STRATS, hosts=["a.com"], tries=3, log_name="0123abcd",
                       **kw)
    enc = inv.args[-1] if kw.get("elevate") == "none" else \
        inv.args[-1].split("'-EncodedCommand','")[1].split("'")[0]
    return inv, base64.b64decode(enc).decode("utf-16-le")


def test_windows_helper_is_embedded_not_a_file(monkeypatch):
    inv, inner = windows_inner(monkeypatch, "tune")
    assert inv.args[:2] == ["powershell", "-NoProfile"] and "-Verb RunAs" in inv.args[-1]
    packed = re.search(r"FromBase64String\('([^']+)'\)", inner).group(1)
    assert gzip.decompress(base64.b64decode(packed)).decode() == \
        runner.helper_text("setup-windows.ps1")
    # Parameter names bare, values quoted; strategies joined with "|".
    assert "-Mode 'tune' -LogName '0123abcd'" in inner and "'-Mode'" not in inner
    assert "-Strategies '--dpi-desync=multisplit|--dpi-desync=fake'" in inner
    assert inv.log.parts[-3:] == ("dpi-dashboard", "logs", "0123abcd.log")
    assert ".ps1" not in inv.args[-1]
    assert len(subprocess.list2cmdline(inv.args)) < runner.WINDOWS_COMMAND_LIMIT


def test_windows_direct_command(monkeypatch):
    inv, inner = windows_inner(monkeypatch, "install", elevate="none")
    assert inv.args[:2] == ["powershell", "-NoProfile"] and "-EncodedCommand" in inv.args
    assert "-Mode 'install'" in inner


def test_windows_log_path_uses_programdata(monkeypatch):
    monkeypatch.setitem(os.environ, "ProgramData", os.path.join("X", "PD"))
    assert runner.windows_log_path("n") == \
        runner.Path("X", "PD", "dpi-dashboard", "logs", "n.log")
