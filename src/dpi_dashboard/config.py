"""User settings, stored as JSON in the per-user config directory."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .setup.strategies import STRATEGIES, is_safe

BACKENDS = ("auto", "systemd", "windows-service")
LANGUAGES = ("auto", "en", "tr")
DEFAULT_HOSTS = ["discord.com", "gateway.discord.gg", "cdn.discordapp.com",
                 "discord.gg", "status.discord.com"]


@dataclass
class Config:
    backend: str = "auto"           # "auto", "systemd" or "windows-service"
    service: str | None = None      # None = try the known names for the backend
    hosts: list[str] = field(default_factory=lambda: list(DEFAULT_HOSTS))
    tries: int = 3
    timeout: float = 6.0
    language: str = "auto"          # "auto", "en" or "tr"
    refresh_seconds: float = 2.0
    strategies: list[str] = field(default_factory=lambda: list(STRATEGIES))  # setup order


def config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "dpi-dashboard" / "config.json"


def load(path: Path | None = None) -> tuple[Config, str | None]:
    """Load settings. Returns (config, warning); bad values fall back to defaults."""
    path = path or config_path()
    cfg = Config()
    if not path.exists():
        return cfg, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level must be an object")
    except (OSError, ValueError) as e:
        return cfg, f"{path}: {e}"
    known = {f.name for f in fields(Config)}
    bad = []
    for k, v in data.items():
        if k not in known:
            bad.append(k)
        elif k == "service" and (v is None or isinstance(v, str)):
            cfg.service = v.strip() if v and v.strip() else None
        elif k == "hosts" and isinstance(v, list) and all(isinstance(h, str) for h in v):
            cfg.hosts = [h.strip() for h in v if h.strip()]
        elif (k == "strategies" and isinstance(v, list) and v
              and all(isinstance(x, str) and is_safe(x.strip()) for x in v)):
            cfg.strategies = [x.strip() for x in v]
        elif k == "backend" and v in BACKENDS:
            cfg.backend = v
        elif k == "language" and v in LANGUAGES:
            cfg.language = v
        elif k == "tries" and type(v) is int:
            cfg.tries = v
        elif k in ("timeout", "refresh_seconds") and type(v) in (int, float) and v > 0:
            setattr(cfg, k, float(v))
        else:
            bad.append(k)
    if cfg.tries < 1:
        cfg.tries, bad = 1, bad + ["tries"]
    return cfg, (f"{path}: ignored {', '.join(sorted(set(bad)))}" if bad else None)


def ensure_file(path: Path | None = None) -> Path:
    """Write the default settings if the file does not exist yet, so users can edit it."""
    path = path or config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(Config()), indent=2) + "\n", encoding="utf-8")
    return path
