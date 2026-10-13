# Changelog

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
