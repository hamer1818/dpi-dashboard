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
import sys

from .. import config
from . import runner, status


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

    inv = runner.build(a.mode, strategies=cfg.strategies, hosts=cfg.hosts,
                       tries=a.tries or cfg.tries, dns_dot=a.dns_dot, elevate=a.elevate)
    done = []

    def show(line: str) -> None:
        print(line, flush=True)
        ev = runner.parse_line(line)
        if ev.kind == "done":
            done.append(ev.args[:1] == ("ok",))

    rc = runner.run(inv, show)
    return 0 if done and done[-1] and rc == 0 else (rc or 1)


if __name__ == "__main__":
    sys.exit(main())
