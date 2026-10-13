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
