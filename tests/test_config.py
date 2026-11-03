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


def test_old_default_hosts_are_upgraded(tmp_path):
    cfg, warn = config.load(write(tmp_path, json.dumps({"hosts": config.OLD_DEFAULT_HOSTS[0]})))
    assert cfg.hosts == config.DEFAULT_HOSTS and not warn
    cfg, _ = config.load(write(tmp_path, json.dumps({"hosts": ["example.com"]})))
    assert cfg.hosts == ["example.com"]


def test_old_default_strategies_are_upgraded(tmp_path):
    from dpi_dashboard.setup.strategies import OLD_DEFAULT_STRATEGIES, STRATEGIES
    cfg, warn = config.load(write(tmp_path, json.dumps({"strategies": OLD_DEFAULT_STRATEGIES[0]})))
    assert cfg.strategies == STRATEGIES and not warn
    cfg, _ = config.load(write(tmp_path, json.dumps({"strategies": ["--dpi-desync=fake"]})))
    assert cfg.strategies == ["--dpi-desync=fake"]
