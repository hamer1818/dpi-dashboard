"""Parse the Windows helper with PowerShell, so syntax errors fail CI on every OS."""

import shutil
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).parents[1] / "src/dpi_dashboard/assets/setup-windows.ps1"
SHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.mark.skipif(SHELL is None, reason="PowerShell not installed")
def test_parses():
    script = (f"$t=$null; $e=$null; [void][System.Management.Automation.Language.Parser]::"
              f"ParseFile('{HELPER}', [ref]$t, [ref]$e); "
              "if ($e.Count) { $e | ForEach-Object { $_.Message }; exit 1 }")
    r = subprocess.run([SHELL, "-NoProfile", "-Command", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def elevated_inner(tmp_path, monkeypatch, mode):
    """The script the UAC-elevated PowerShell runs, decoded from the real command."""
    import base64

    from dpi_dashboard.setup import runner
    monkeypatch.setattr(runner.sys, "platform", "win32")
    cmd = runner.build_command(HELPER, mode, tmp_path / "log", hosts=["discord.com"], tries=1)
    enc = cmd[-1].split("'-EncodedCommand','")[1].split("'")[0]
    script = tmp_path / "inner.ps1"
    script.write_text(base64.b64decode(enc).decode("utf-16-le"), encoding="utf-8-sig")
    (tmp_path / "log").write_text("")
    (tmp_path / "pf").mkdir()
    return script


@pytest.mark.skipif(SHELL is None, reason="PowerShell not installed")
@pytest.mark.parametrize("mode, expected", [
    ("tune", "@@ERROR the zapret service was not installed by DPI Dashboard"),   # helper ran
    ("bogus", "@@ERROR Cannot validate argument on parameter 'Mode'"),         # caught before
])
def test_elevated_command_reaches_the_helper(tmp_path, monkeypatch, mode, expected):
    import os
    script = elevated_inner(tmp_path, monkeypatch, mode)
    r = subprocess.run([SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True,
                       env={**os.environ, "ProgramFiles": str(tmp_path / "pf")})
    log = (tmp_path / "log").read_text(encoding="utf-8-sig")
    assert r.returncode == 1, r.stdout + r.stderr
    assert expected in log and "@@DONE fail" in log
