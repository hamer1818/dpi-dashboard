# Third-party notices

DPI Dashboard's own source code is under the [MIT license](LICENSE).

## The Windows program (`dpi-dashboard-*-windows-x64.exe`)

The Windows program is a single file built with PyInstaller. Besides DPI Dashboard it
contains the components below. Because PyQt6 is licensed under the GNU GPL v3, **the
Windows program as a whole is distributed under the GNU GPL v3** ([licenses/GPL-3.0.txt](licenses/GPL-3.0.txt)).
The license texts are included in the program, in this repository and in the
`*-licenses.zip` file of every release.

| Component | Version | License | Source code |
|---|---|---|---|
| PyQt6 (Riverbank Computing) | 6.11.0 | GPL-3.0-only | <https://pypi.org/project/PyQt6/6.11.0/#files> |
| Qt 6 (The Qt Company), as PyQt6-Qt6 | 6.11.2 | LGPL-3.0 | <https://download.qt.io/official_releases/qt/> |
| PyQt6-sip (Riverbank Computing) | 13.13.0 | BSD-2-Clause | <https://pypi.org/project/PyQt6-sip/13.13.0/#files> |
| Python runtime | 3.12 | PSF-2.0 | <https://www.python.org/downloads/source/> |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with the Bootloader Exception (no conditions on the built program) | <https://github.com/pyinstaller/pyinstaller> |

The exact versions are pinned in
[`packaging/requirements/release-windows.txt`](packaging/requirements/release-windows.txt).
The source code of DPI Dashboard for a given release is this repository at that release's
tag. Under the LGPL you may replace Qt in the program: build it yourself from this
source with a Qt / PyQt6 of your choice, as described in the README.

## The Python package and the Linux install

The wheel, the source archive and `scripts/install-linux.sh` contain only DPI Dashboard
(MIT). PyQt6 is installed separately, as a dependency, under its own license.

## Downloaded at setup, not distributed with DPI Dashboard

The **Setup** button downloads these directly from their publisher onto the user's
computer. They are listed for information only:

| Component | License | Source |
|---|---|---|
| zapret (bol-van) | MIT | <https://github.com/bol-van/zapret> |
| WinDivert (basil00), part of zapret for Windows | LGPL-3.0 or GPL-2.0 | <https://github.com/basil00/WinDivert> |
| Cygwin DLL (Red Hat), part of zapret for Windows | LGPL-3.0 | <https://cygwin.com/> |
