# Changelog

## 0.1.0

First public release.

- Turn a DPI-bypass service on and off (start + enable at boot / stop + disable).
- Backends: systemd units on Linux (polkit/pkexec), Windows services (UAC).
- Connection test with failure reasons: reset, timeout, DNS, certificate, TLS.
- Settings file, English and Turkish UI.
- Linux user-level install script; Windows single-file executable built in CI.
