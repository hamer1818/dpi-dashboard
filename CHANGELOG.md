# Changelog

## 0.5.2

- **Linux: Setup failed with "invalid host" on systems in Turkish.** In the tr_TR locale,
  which `pkexec` passes to the helper, `[A-Za-z]` does not contain the letter "i", so
  `discord.com` failed the host check. The helper now runs with `LC_ALL=C`.
- README (English and Turkish) rewritten as step-by-step guides for Windows and Linux,
  with new screenshots made from the real widgets (`scripts/screenshots.py`).
- `uninstall-linux.sh` also removes the "Start when I log in" entry.

## 0.5.1

(0.5.0 was tagged but never released: its Windows DNS check failed in CI. Its changes
are all here.)

- **System tray.** The icon shows the state (green on, gray off, red missing); its menu
  turns the service on or off, runs the test, shows the window or quits. Closing the
  window keeps the app in the tray (setting `close_to_tray`).
- **Start at login**, straight into the tray: **Settings → Start when I log in**
  (Windows: the current user's Run key; Linux: an XDG autostart entry). New
  `--minimized` option.
- **Automatic updates** from the GitHub releases (setting `auto_update`, on by default,
  checked at start and every 12 hours, or **Settings → Check for updates now**). The
  Windows program and the Linux user install download the new version, verify it against
  the release's `SHA256SUMS` and GitHub's own checksum, and install it when the app
  restarts (**Restart now**) or quits. Other installs only get a notice with a link.
- Only one window per user: starting the app again brings the running one to the front.
- Windows: the DNS change could fail with "Exception setting NetAdapter" on machines
  where an interface has more than one adapter object; connected adapters are now found
  from the default routes.
- The **Settings** button is now a menu; the settings file opens from there.
- Build: PyQt6 6.12.0 / Qt 6.12.0, setuptools 84.2.1. CI is a single workflow; the release
  is only published when all tests and setup checks pass.

## 0.4.1

- New strategy list, measured on Turk Telekom: strategies that send a fake request first
  (`fake` with `md5sig` / `badseq` and a randomized fake TLS hello, or `autottl`) reached
  every Discord site; the old first choice, splitting alone, did on Linux but only got
  6 of 18 connections through with winws on Windows. Settings files with the old default
  list get the new one; run **Find the best setting again** to use it.

## 0.4.0

- **Discord works fully, not just partly.** The service only handled HTTPS on TCP 443.
  It now also covers Discord voice over UDP (STUN and IP discovery, 19294-19344 and
  50000-50100), QUIC (UDP 443) and Cloudflare's extra TLS ports (2053, 2083, 2087, 2096,
  8443), on Windows and Linux.
- Setup in the window now always switches to DNS that cannot be forged, listed in the
  confirmation (the checkbox is gone; the command line keeps `--dns-dot`). Windows:
  Cloudflare DNS on the connected adapters, DNS over HTTPS on Windows 11; Remove
  restores the previous servers. Before, Windows only showed how to change DNS by hand,
  which does not apply to Windows 10. Linux: DNS-over-TLS in systemd-resolved, as before.
- Setup warns when even the best strategy misses some test sites, instead of reporting
  plain success.
- More Discord test sites (`media.discordapp.net`, `updates.discord.com`); settings files
  that still have the old default list get the new one.

## 0.3.1

- Licensing made explicit. The source code stays MIT. The Windows program contains PyQt6
  (GPL-3.0), Qt 6 (LGPL-3.0), PyQt6-sip (BSD-2-Clause) and Python (PSF-2.0), so the
  `.exe` as a whole is distributed under the GNU GPL v3. Added `THIRD_PARTY_NOTICES.md`
  with every bundled part, its license and its source, the license texts in `licenses/`
  (also inside the `.exe` and as `*-licenses.zip` in each release), and an
  **About and licenses** link in the window.

## 0.3.0 — security

- **Nothing a normal user can write is executed or trusted with administrator rights.**
  Before, setup downloaded and verified zapret as the user and then ran the helper script
  and zapret's install scripts as root from that user-writable folder, which another
  program running as the user could change in between (and zapret's `sha256sum.txt` does
  not cover its scripts). Now:
  - the helper script is piped into `pkexec /bin/bash` (Linux) or compressed into the
    elevated command line (Windows), never read from a file;
  - the helper downloads zapret itself into a folder only root / administrators can
    write, checks the GitHub SHA-256 and upstream's `sha256sum.txt` there, and refuses
    unsafe archive paths and links;
  - Linux progress comes back on stdout, not through a log file root wrote to without
    checking the path. On Windows the log lives in `%ProgramData%\dpi-dashboard\logs`,
    locked so users can read but not write; a folder planted there beforehand (wrong
    owner, or a junction) is moved aside, never followed.
- Release builds: GitHub Actions pinned to commit SHAs, read-only tokens except for
  publishing, hash-locked build dependencies, `SHA256SUMS` and signed build provenance;
  the third-party release action was replaced by the GitHub CLI. Dependabot keeps the
  pins up to date.
- `SECURITY.md` and a Security section in the README.

## 0.2.2

- Setup works on minimal Linux installs: it no longer needs `pgrep` (missing on
  Fedora and Debian containers, where every strategy looked like it failed to start)
  and installs `gawk` when `awk` is missing (openSUSE).
- Fedora/RHEL: `/opt/zapret` is relabelled with `restorecon` when SELinux is enabled.
- CI runs the full setup on Debian 12, Fedora, Arch Linux and openSUSE Tumbleweed in
  addition to Ubuntu and Windows.
- README: which systems are tested, expected to work, or not supported, and why.

## 0.2.1

- Windows: Setup failed right after the download without asking for administrator
  rights or showing an error. The elevated command quoted the parameter names, so
  PowerShell did not recognise them and the helper stopped before writing anything.
- Errors that happen before the helper starts are now written to the setup log, and an
  administrator step that ends silently is reported with its exit code.
- The DNS check says why it could not be done.
- CI now runs the Windows setup through the same RunAs path users go through.

## 0.2.0

- **Setup** button for computers that have no bypass service yet:
  - checks the service, the zapret files, missing tools and whether DNS answers look forged;
  - downloads the latest zapret release, verifies the archive against GitHub's SHA-256 and
    every program against upstream's `sha256sum.txt`;
  - installs it as a service (Linux: `/opt/zapret` + `zapret.service`, missing `curl` /
    `nftables` from the package manager; Windows: `%ProgramFiles%\zapret` + `zapret`
    service), asking for the administrator password once;
  - measures the blocking, tries strategies until one reaches every test site, keeps it
    and turns the service on; restores the previous settings if none works;
  - **Find the best setting again** for an existing install, **Remove** for what it
    installed. Installs from packages or other tools are never deleted.
  - Linux: optional DNS-over-TLS in systemd-resolved when DNS looks forged.
- `strategies` setting; `python -m dpi_dashboard.setup` command line.
- Windows: also detects the `winws1` service of zapret-win-bundle.
- CI runs a real install, retune and removal on fresh Ubuntu and Windows machines.

## 0.1.0

First public release.

- Turn a DPI-bypass service on and off (start + enable at boot / stop + disable).
- Backends: systemd units on Linux (polkit/pkexec), Windows services (UAC).
- Connection test with failure reasons: reset, timeout, DNS, certificate, TLS.
- Settings file, English and Turkish UI.
- Linux user-level install script; Windows single-file executable built in CI.
