"""The Windows helper: syntax, and the real embedded command run through PowerShell.

On Windows CI this is Windows PowerShell 5.1, the version users have. On Linux it runs
with pwsh if installed; the ACL part of the helper is skipped there.
"""

import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from dpi_dashboard.setup import runner

HELPER = Path(__file__).parents[1] / "src/dpi_dashboard/assets/setup-windows.ps1"
SHELL = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(SHELL is None, reason="PowerShell not installed")


@needs_ps
def test_parses():
    script = (f"$t=$null; $e=$null; [void][System.Management.Automation.Language.Parser]::"
              f"ParseFile('{HELPER}', [ref]$t, [ref]$e); "
              "if ($e.Count) { $e | ForEach-Object { $_.Message }; exit 1 }")
    r = subprocess.run([SHELL, "-NoProfile", "-Command", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def run_embedded(tmp_path, monkeypatch, mode, **kw):
    """Build the elevated command the app would use and run its inner script directly."""
    monkeypatch.setattr(runner.sys, "platform", "win32")
    pd, pf = tmp_path / "ProgramData", tmp_path / "ProgramFiles"
    pd.mkdir()
    pf.mkdir()
    monkeypatch.setitem(os.environ, "ProgramData", str(pd))
    inv = runner.build(mode, strategies=["--dpi-desync=fake"], hosts=["discord.com"], tries=1,
                       log_name="testlog01", **kw)
    enc = inv.args[-1].split("'-EncodedCommand','")[1].split("'")[0]
    script = tmp_path / "inner.ps1"
    script.write_text(base64.b64decode(enc).decode("utf-16-le"), encoding="utf-8-sig")
    r = subprocess.run([SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True,
                       env={**os.environ, "ProgramData": str(pd), "ProgramFiles": str(pf)})
    log = inv.log.read_text(encoding="utf-8-sig") if inv.log.exists() else ""
    return r, log, inv


@needs_ps
def test_embedded_helper_runs_and_logs(tmp_path, monkeypatch):
    r, log, inv = run_embedded(tmp_path, monkeypatch, "tune")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "@@ERROR the zapret service was not installed by DPI Dashboard" in log
    assert inv.log.parent == tmp_path / "ProgramData" / "dpi-dashboard" / "logs"


@needs_ps
def test_bad_arguments_are_reported_in_the_log(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "valid_strategies", lambda s: ["--ok"])
    r, log, _ = run_embedded(tmp_path, monkeypatch, "bogus")
    assert r.returncode == 1 and "@@ERROR unknown mode" in log


@needs_ps
def test_untrusted_log_folder_is_moved_aside(tmp_path, monkeypatch):
    """A folder planted in place of ours (here: a link) is renamed, never followed."""
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("precious")
    pd = tmp_path / "ProgramData"
    pd.mkdir()
    try:
        (pd / "dpi-dashboard").symlink_to(victim, target_is_directory=True)
    except OSError:
        pytest.skip("cannot create directory links here")
    monkeypatch.setattr(runner.sys, "platform", "win32")
    r, log, inv = run_embedded_existing(tmp_path, monkeypatch, pd)
    assert (victim / "keep.txt").read_text() == "precious"
    assert not any(victim.glob("logs"))                  # nothing written through the link
    assert inv.log.exists() and not (pd / "dpi-dashboard").is_symlink()
    assert any(p.name.startswith("dpi-dashboard.untrusted-") for p in pd.iterdir())


def run_embedded_existing(tmp_path, monkeypatch, pd):
    pf = tmp_path / "ProgramFiles"
    pf.mkdir(exist_ok=True)
    monkeypatch.setitem(os.environ, "ProgramData", str(pd))
    inv = runner.build("tune", strategies=["--dpi-desync=fake"], hosts=["discord.com"], tries=1,
                       log_name="testlog02")
    enc = inv.args[-1].split("'-EncodedCommand','")[1].split("'")[0]
    script = tmp_path / "inner2.ps1"
    script.write_text(base64.b64decode(enc).decode("utf-16-le"), encoding="utf-8-sig")
    r = subprocess.run([SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True,
                       env={**os.environ, "ProgramData": str(pd), "ProgramFiles": str(pf)})
    log = inv.log.read_text(encoding="utf-8-sig") if inv.log.exists() else ""
    return r, log, inv


@needs_ps
def test_logging_does_not_leak_into_return_values(tmp_path):
    """A function that logs must still return only its own value."""
    text = HELPER.read_text(encoding="utf-8")
    log_fn = text[text.index("function Log("):text.index("function Fail(")]
    script = tmp_path / "t.ps1"
    script.write_text("$Log = $null\n" + log_fn +
                      "function Get-Path { Log 'step'; return 'C:\\x' }\n"
                      "function Start-It { Log 'start failed'; return $false }\n"
                      "if ((Get-Path) -ne 'C:\\x') { exit 3 }\n"
                      "if (Start-It) { exit 4 }\n"
                      "exit 0\n", encoding="utf-8-sig")
    r = subprocess.run([SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
