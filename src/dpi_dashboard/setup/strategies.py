"""Candidate nfqws/winws strategies for HTTPS (port 443), tried in this order.

The same option syntax works for nfqws (Linux) and winws (Windows). Measured on Turk
Telekom on 2026-11-03 with nfqws (30 connections to five Discord sites each, 10/30
without a bypass). The blocking there is not on every connection, so a single short
measurement can look better or worse than a strategy is; the order puts the ones that
reached 30/30 first, with fakes the DPI takes for the real request, then splits without
fakes. Splits alone (the old first choice) reached 29/30 on Linux but only 6/18 with winws
on the same network.
"""

from __future__ import annotations

import re

STRATEGIES: list[str] = [
    "--dpi-desync=fake,multidisorder --dpi-desync-split-pos=1,midsld --dpi-desync-repeats=11 "
    "--dpi-desync-fooling=md5sig --dpi-desync-fake-tls-mod=rnd,dupsid,sni=www.google.com",
    "--dpi-desync=fake,multidisorder --dpi-desync-split-pos=midsld --dpi-desync-repeats=6 "
    "--dpi-desync-fooling=badseq --dpi-desync-fake-tls-mod=rnd,dupsid,sni=www.google.com",
    "--dpi-desync=fake --dpi-desync-fooling=md5sig --dpi-desync-repeats=6",
    "--dpi-desync=fake,multidisorder --dpi-desync-split-pos=1,midsld --dpi-desync-autottl",
    "--dpi-desync=fake,multisplit --dpi-desync-split-pos=1 --dpi-desync-fooling=md5sig",
    "--dpi-desync=fake --dpi-desync-autottl",
    "--dpi-desync=fake --dpi-desync-ttl=4",
    "--dpi-desync=multidisorder --dpi-desync-split-pos=2 --dpi-desync-split-seqovl=1",
    "--dpi-desync=fake,multidisorder --dpi-desync-split-pos=midsld --dpi-desync-fooling=badseq",
    "--dpi-desync=multidisorder --dpi-desync-split-pos=1,midsld",
]

# Written to config.json by earlier versions; replaced by the current list on load.
OLD_DEFAULT_STRATEGIES: list[list[str]] = [[
    "--dpi-desync=multidisorder --dpi-desync-split-pos=2 --dpi-desync-split-seqovl=1",
    "--dpi-desync=multisplit --dpi-desync-split-pos=2 --dpi-desync-split-seqovl=1",
    "--dpi-desync=multidisorder --dpi-desync-split-pos=1,midsld",
    "--dpi-desync=fake,multidisorder --dpi-desync-split-pos=midsld --dpi-desync-fooling=badseq",
    "--dpi-desync=fakedsplit --dpi-desync-split-pos=1 --dpi-desync-fooling=badseq",
]]

# Strategies end up in a shell-sourced config file (Linux) and in a service command line
# (Windows), so only plain option characters are allowed: no quotes, $, ;, backticks.
SAFE = re.compile(r"^--[A-Za-z0-9 =,._+:/-]+$")


def is_safe(strategy: str) -> bool:
    return bool(SAFE.match(strategy)) and "  " not in strategy.strip()
