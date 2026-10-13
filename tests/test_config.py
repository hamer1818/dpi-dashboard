import json

from dpi_dashboard import config


def write(tmp_path, data):
    p = tmp_path / "config.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def test_missing_file_gives_defaults(tmp_path):
    cfg, warn = config.load(tmp_path / "nope.json")
    assert cfg == config.Config() and warn is None


def test_valid_values(tmp_path):
    cfg, warn = config.load(write(tmp_path, {
        "backend": "windows-service", "service": "GoodbyeDPI", "hosts": [" a.com ", ""],
        "tries": 2, "timeout": 3, "language": "tr"}))
    assert warn is None
    assert (cfg.backend, cfg.service, cfg.hosts, cfg.tries, cfg.timeout, cfg.language) == \
        ("windows-service", "GoodbyeDPI", ["a.com"], 2, 3.0, "tr")


def test_bad_values_fall_back(tmp_path):
    cfg, warn = config.load(write(tmp_path, {
        "backend": "openrc", "tries": "3", "language": "de", "unknown": 1, "timeout": -1}))
    assert cfg.backend == "auto" and cfg.tries == 3 and cfg.language == "auto"
    assert cfg.timeout == config.Config().timeout
    for key in ("backend", "tries", "language", "unknown", "timeout"):
        assert key in warn


def test_broken_json(tmp_path):
    cfg, warn = config.load(write(tmp_path, "{not json"))
    assert cfg == config.Config() and warn


def test_ensure_file_writes_defaults(tmp_path):
    p = config.ensure_file(tmp_path / "sub" / "config.json")
    assert json.loads(p.read_text(encoding="utf-8"))["hosts"] == config.DEFAULT_HOSTS
