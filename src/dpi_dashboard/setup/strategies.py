"""Candidate nfqws/winws strategies for HTTPS (port 443), tried in this order.

The same option syntax works for nfqws (Linux) and winws (Windows). The first entry is
the one verified on Turk Telekom; the rest are common alternatives from the zapret
documentation. Options that need per-network calibration (autottl, md5sig, ts,
datanoack) are left out on purpose.
"""

from __future__ import annotations

import re

STRATEGIES: list[str] = [
    "--dpi-desync=multidisorder --dpi-desync-split-pos=2 --dpi-desync-split-seqovl=1",
    "--dpi-desync=multisplit --dpi-desync-split-pos=2 --dpi-desync-split-seqovl=1",
    "--dpi-desync=multidisorder --dpi-desync-split-pos=1,midsld",
    "--dpi-desync=fake,multidisorder --dpi-desync-split-pos=midsld --dpi-desync-fooling=badseq",
    "--dpi-desync=fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq",
]

# Strategies end up in a shell-sourced config file (Linux) and in a service command line
# (Windows), so only plain option characters are allowed: no quotes, $, ;, backticks.
SAFE = re.compile(r"^--[A-Za-z0-9 =,._+:/-]+$")


def is_safe(strategy: str) -> bool:
    return bool(SAFE.match(strategy)) and "  " not in strategy.strip()
