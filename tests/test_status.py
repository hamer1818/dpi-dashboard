import io
import json

from dpi_dashboard.setup import status


def doh(answers):
    body = json.dumps({"Answer": [{"type": 1, "data": a} for a in answers]}).encode()

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass
    return lambda req, timeout=None: R(body)


def test_dns_ok(monkeypatch):
    monkeypatch.setattr(status, "system_addresses", lambda h: ["1.1.1.1", "2.2.2.2"])
    assert status.check_dns("x", opener=doh(["2.2.2.2"])).state == "ok"


def test_dns_mismatch(monkeypatch):
    monkeypatch.setattr(status, "system_addresses", lambda h: ["195.175.254.2"])
    d = status.check_dns("x", opener=doh(["162.159.1.1"]))
    assert d.state == "mismatch" and d.system == ["195.175.254.2"]


def test_dns_unknown_when_doh_fails(monkeypatch):
    monkeypatch.setattr(status, "system_addresses", lambda h: ["1.1.1.1"])

    def boom(req, timeout=None):
        raise OSError("blocked")
    assert status.check_dns("x", opener=boom).state == "unknown"


def test_install_and_tune_rules():
    fresh = status.SetupStatus("linux")
    assert fresh.can_install and not fresh.can_tune
    pkg = status.SetupStatus("linux", service_found=True, files_present=True)
    assert not pkg.can_install and pkg.can_tune
    foreign_win = status.SetupStatus("windows", service_found=True)
    assert not foreign_win.can_install and not foreign_win.can_tune
    ours_win = status.SetupStatus("windows", service_found=True, files_present=True, managed=True)
    assert ours_win.can_tune
    blocked = status.SetupStatus("linux", missing_required=["systemd"])
    assert not blocked.can_install and not blocked.can_tune
