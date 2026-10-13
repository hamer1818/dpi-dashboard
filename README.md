# DPI Dashboard

[Türkçe](README.tr.md)

A small desktop window to **turn a DPI-bypass service on and off** and **check whether it
actually works** — without touching a terminal.

![DPI Dashboard](docs/screenshot-en.png)

Some internet providers block sites with deep packet inspection (DPI): the connection is
cut in the middle of the TLS handshake as soon as the site name is seen. Tools like
[zapret](https://github.com/bol-van/zapret) and [GoodbyeDPI](https://github.com/ValdikSS/GoodbyeDPI)
get around this, but they run as system services that you normally start and stop from
the command line. DPI Dashboard is a front end for that service.

> **DPI Dashboard does not bypass anything by itself.** It controls a bypass service you
> have already installed. See [Requirements](#requirements).

## Features

- One button to turn the service on or off. It also sets whether it starts at boot.
- Live status: on/off and whether it starts at boot.
- Connection test against a list of sites (Discord by default), several attempts each.
  It tells *how* a failed attempt failed: connection reset (the usual DPI signature),
  timeout, DNS failure, or a rejected certificate.
- Asks for the administrator password each time (polkit on Linux, UAC on Windows).
  No permanent "passwordless" rule is installed.
- English and Turkish, picked from the system language.
- Linux (systemd) and Windows.

## Requirements

| | Linux | Windows 10 / 11 |
|---|---|---|
| Bypass service | `zapret.service` from [zapret](https://github.com/bol-van/zapret) (`install_easy.sh`, or the AUR `zapret` / `zapret-git` packages) | A Windows service named `zapret` (e.g. the `service.bat` of [zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube)) or `GoodbyeDPI` (the `service_install_*.cmd` scripts of GoodbyeDPI) |
| Service manager | systemd | Windows services |
| Password prompt | polkit with an authentication agent (KDE and GNOME have one) | UAC |
| Python (only when not using the `.exe`) | 3.10+ with PyQt6 | 3.10+ with PyQt6 |

If your service has a different name, set it in the [settings file](#settings).

Not supported: Linux systems without systemd (OpenRC, runit, s6), macOS.

## Install

### Linux

```bash
git clone https://github.com/hamer1818/dpi-dashboard.git
cd dpi-dashboard
./scripts/install-linux.sh
```

Then search for **DPI Dashboard** in your application menu (`dpi`, `zapret` and
`discord` also find it). Everything goes into your home directory; no root is needed.
If PyQt6 is already installed from your distribution (`python-pyqt6`, `python3-pyqt6`),
it is reused. To remove it: `./scripts/uninstall-linux.sh`.

Debian/Ubuntu may need `sudo apt install python3-venv` first.

### Windows

Download `dpi-dashboard-<version>-windows-x64.exe` from
[Releases](https://github.com/hamer1818/dpi-dashboard/releases) and run it. No install
step.

The file is not code-signed, so SmartScreen may warn about an unknown publisher:
choose **More info → Run anyway**. You can also build it yourself, see
[Development](#development).

### With pip

```bash
pip install git+https://github.com/hamer1818/dpi-dashboard.git
dpi-dashboard
```

This does not add a menu entry on Linux; use the install script for that.

## Settings

The **Settings** button opens the settings file, creating it with defaults on first
use:

- Linux: `~/.config/dpi-dashboard/config.json`
- Windows: `%APPDATA%\dpi-dashboard\config.json`

```json
{
  "backend": "auto",
  "service": null,
  "hosts": ["discord.com", "gateway.discord.gg", "cdn.discordapp.com",
            "discord.gg", "status.discord.com"],
  "tries": 3,
  "timeout": 6.0,
  "language": "auto",
  "refresh_seconds": 2.0
}
```

| Key | Meaning |
|---|---|
| `backend` | `auto`, `systemd` or `windows-service` |
| `service` | Service name. `null` tries the known names (`zapret.service` on Linux; `zapret`, then `GoodbyeDPI` on Windows). |
| `hosts` | Sites used by the connection test. Put the sites you care about here. |
| `tries` | Attempts per site. DPI blocking is often intermittent, so one attempt is not enough. |
| `timeout` | Seconds per attempt. |
| `language` | `auto`, `en` or `tr` |
| `refresh_seconds` | How often the status is re-read. |

Invalid values are ignored and reported in the window. Restart the app after editing.

## How it works

- **Status** is read without privileges: `systemctl show` on Linux, `sc query` /
  `sc qc` on Windows.
- **On/off** runs `systemctl enable|disable --now <service>` through `pkexec` on Linux,
  and `Set-Service` + `Start-Service` / `Stop-Service` in an elevated PowerShell on
  Windows. "On" also means "start at boot"; "off" sets the service to manual start.
- **The connection test** opens a TLS connection to each site, sends one HTTP `HEAD`
  request and counts any HTTP answer (including redirects and errors like 404) as
  reachable. It uses only the Python standard library, so it works the same on every
  system.

## Troubleshooting

**"NOT FOUND".** The service is not installed, or it has another name. Check with
`systemctl list-unit-files | grep -i zapret` (Linux) or `sc query state= all | findstr /i "zapret goodbye"`
(Windows) and put the name in the settings file.

**Nothing happens when I press the button (Linux).** No polkit authentication agent is
running. Desktop environments like KDE and GNOME start one; minimal window managers
need one added (for example `polkit-gnome` or `lxqt-policykit`).

**The service is on but sites still fail with "connection reset".** The bypass strategy
does not match how your provider blocks. That is configured in zapret/GoodbyeDPI itself
(zapret's `blockcheck.sh` helps you find one); DPI Dashboard only turns the service on
and off.

**"name not resolved (DNS)" or wrong results only for some sites.** Some providers also
falsify DNS answers, which a DPI bypass does not fix. Use encrypted DNS: DNS over HTTPS
in Windows 11 network settings or your browser, or `DNSOverTLS=yes` in
systemd-resolved on Linux.

**"certificate rejected".** Something between you and the site is presenting a different
certificate. Treat that connection as untrusted.

## Legal note

Whether bypassing network filtering is allowed depends on where you are. You are
responsible for how you use this software. It is provided without warranty, see the
[license](LICENSE).

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
QT_QPA_PLATFORM=offscreen pytest
ruff check .
```

Build the Windows executable (on Windows):

```bash
pip install . pyinstaller
pyinstaller --onefile --windowed --name dpi-dashboard --icon src/dpi_dashboard/assets/icon.ico --collect-data dpi_dashboard packaging/windows/entry.py
```

New backends live in `src/dpi_dashboard/backends/`: implement `state()` and
`set_enabled()` from `Backend` and register the class in `KINDS`.

Bug reports and pull requests are welcome. If you use a bypass tool with a service name
that is not detected automatically, please open an issue with the name.

## License

[MIT](LICENSE)
