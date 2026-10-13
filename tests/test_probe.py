import socket
import ssl
import struct
import threading
from pathlib import Path

from dpi_dashboard import probe

DATA = Path(__file__).parent / "data"


def serve_once(handler):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        conn, _ = srv.accept()
        try:
            handler(conn)
        finally:
            srv.close()

    threading.Thread(target=run, daemon=True).start()
    return port


def client_context():
    return ssl.create_default_context(cafile=str(DATA / "localhost.crt"))


def test_reachable_over_tls():
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(DATA / "localhost.crt", DATA / "localhost.key")

    def handler(conn):
        with sctx.wrap_socket(conn, server_side=True) as t:
            t.recv(1024)
            t.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")

    port = serve_once(handler)
    a = probe.check_host("localhost", port, timeout=5, context=client_context())
    assert a.ok, a


def test_reset_during_handshake():
    def handler(conn):
        conn.recv(1024)  # the ClientHello, which carries the server name
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        conn.close()     # SO_LINGER 0 -> RST, like a DPI box

    port = serve_once(handler)
    a = probe.check_host("localhost", port, timeout=5, context=client_context())
    assert not a.ok and a.reason == probe.RESET


def test_timeout():
    stop = threading.Event()
    port = serve_once(lambda conn: stop.wait(3))
    a = probe.check_host("localhost", port, timeout=0.5, context=client_context())
    stop.set()
    assert not a.ok and a.reason == probe.TIMEOUT


def test_dns_failure():
    a = probe.check_host("does-not-exist.invalid", timeout=5)
    assert not a.ok and a.reason == probe.DNS


def test_host_result_summary():
    r = probe.HostResult("x", [probe.Attempt(True), probe.Attempt(False, probe.RESET),
                               probe.Attempt(False, probe.TIMEOUT)])
    assert r.successes == 1
    assert r.reasons == [probe.RESET, probe.TIMEOUT]
