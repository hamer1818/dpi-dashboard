"""Command line for the setup, used by CI and for scripting.

    python -m dpi_dashboard.setup check
    python -m dpi_dashboard.setup install   [--elevate auto|sudo|none] [--dns-dot]
    python -m dpi_dashboard.setup tune      [--elevate ...] [--dns-dot]
    python -m dpi_dashboard.setup uninstall [--elevate ...]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys

from .. import config
from . import runner, status, upstream


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dpi_dashboard.setup")
    ap.add_argument("mode", choices=["check", "install", "tune", "uninstall"])
    ap.add_argument("--elevate", choices=["auto", "sudo", "none"], default="auto")
    ap.add_argument("--dns-dot", action="store_true", help="Linux: turn on DNS-over-TLS")
    ap.add_argument("--tries", type=int, help="attempts per site (default from settings)")
    a = ap.parse_args(argv)
    cfg, warning = config.load()
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    if a.mode == "check":
        st = status.check(cfg.service, cfg.hosts[0] if cfg.hosts else None)
        print(json.dumps(dataclasses.asdict(st), indent=2))
        return 0

    work = runner.workdir()
    log = work / "setup.log"
    log.touch()
    source = None
    if a.mode == "install":
        archive = "zip" if sys.platform == "win32" else "tar.gz"
        try:
            _, source = upstream.prepare(work, archive, log=print)
        except (upstream.SetupError, OSError) as e:
            print(f"download failed: {e}", file=sys.stderr)
            return 1
    cmd = runner.build_command(
        runner.stage_helper(work), a.mode, log, source=source,
        strategies=runner.write_strategies(work, cfg.strategies) if a.mode != "uninstall" else None,
        hosts=cfg.hosts, tries=a.tries or cfg.tries, dns_dot=a.dns_dot, elevate=a.elevate)
    # The helper also prints to stdout, except when elevated through UAC; read the log then.
    rc = subprocess.call(cmd)
    if sys.platform == "win32" and a.elevate != "none":
        print(log.read_text(encoding="utf-8", errors="replace"))
    done = [runner.parse_line(x) for x in log.read_text(encoding="utf-8").splitlines()]
    ok = any(e.kind == "done" and e.args[:1] == ("ok",) for e in done)
    return 0 if ok and rc == 0 else (rc or 1)


if __name__ == "__main__":
    sys.exit(main())
