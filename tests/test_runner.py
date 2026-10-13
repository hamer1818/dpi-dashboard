import base64
import sys

import pytest

from dpi_dashboard.setup import runner


def test_parse_protocol_lines():
    assert runner.parse_line("@@TRY 2 14/15\n") == runner.Event("try", ("2", "14/15"))
    assert runner.parse_line("@@DONE ok") == runner.Event("done", ("ok",))
    assert runner.parse_line("@@ERROR no strategy worked; x") == \
        runner.Event("error", ("no", "strategy worked; x"))
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


def test_write_strategies_drops_unsafe(tmp_path):
    p = runner.write_strategies(tmp_path, ["--dpi-desync=fake", "--x=$(reboot)", 'bad"'])
    assert p.read_text().splitlines() == ["--dpi-desync=fake"]
    with pytest.raises(ValueError):
        runner.write_strategies(tmp_path, ["rm -rf /"])


@pytest.mark.skipif(sys.platform == "win32", reason="Linux command")
def test_linux_command(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.os, "geteuid", lambda: 1000)
    cmd = runner.build_command(tmp_path / "h.sh", "install", tmp_path / "log",
                               source=tmp_path / "src", strategies=tmp_path / "s.txt",
                               hosts=["a.com", "b.com"], tries=2, dns_dot=True)
    assert cmd[:3] == ["pkexec", "/bin/bash", str(tmp_path / "h.sh")]
    assert cmd[3:5] == ["install", str(tmp_path / "log")]
    assert cmd[cmd.index("--hosts") + 1] == "a.com b.com" and "--dns-dot" in cmd
    none = runner.build_command(tmp_path / "h.sh", "tune", tmp_path / "log", elevate="none")
    assert none[0] == "/bin/bash"


def test_windows_command(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    helper = tmp_path / "it's here" / "setup.ps1"
    cmd = runner.build_command(helper, "tune", tmp_path / "log", hosts=["a.com"], tries=3)
    assert cmd[:2] == ["powershell", "-NoProfile"]
    enc = cmd[-1].split("'-EncodedCommand','")[1].split("'")[0]
    inner = base64.b64decode(enc).decode("utf-16-le")
    assert "'" + str(helper).replace("'", "''") + "'" in inner   # quoted for PowerShell
    # Parameter names must be bare: a quoted '-Mode' is bound as a plain string.
    assert "-Mode 'tune'" in inner and "'-Mode'" not in inner
    assert "@@ERROR" in inner              # failures before the helper runs reach the log
    direct = runner.build_command(helper, "tune", tmp_path / "log", elevate="none")
    assert direct[direct.index("-File") + 1] == str(helper)
