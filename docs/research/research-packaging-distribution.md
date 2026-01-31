# Packaging & Distribution Research: PySide6 Worldbuilding Application on Windows

> **Research date:** January 2026
> **Target:** Standalone Windows .exe installer for non-technical users
> **Application stack:** PySide6 GUI, Python engine modules, JSON data files, SQLite database, reference text files

---

## Table of Contents

1. [PyInstaller with PySide6](#1-pyinstaller-with-pyside6)
2. [Alternative Packagers](#2-alternative-packagers)
3. [Bundle Size Optimization](#3-bundle-size-optimization)
4. [Installer Creation](#4-installer-creation)
5. [Auto-Updates](#5-auto-updates)
6. [Data File Management](#6-data-file-management)
7. [Code Signing](#7-code-signing)
8. [Prerequisites & Runtime Dependencies](#8-prerequisites--runtime-dependencies)

---

## 1. PyInstaller with PySide6

### Overview

PyInstaller (current version 6.18.0 as of January 2026) is the most widely used tool for packaging PySide6 applications into standalone Windows executables. It bundles the Python interpreter, all dependencies, and application code into a distributable package. PySide6 is supported out of the box via built-in hooks.

### One-File vs. One-Directory Mode

| Aspect | `--onefile` | `--onedir` (default) |
|--------|-------------|----------------------|
| **Output** | Single `.exe` file | Folder containing `.exe` + libraries |
| **Startup time** | 2-10 seconds (must extract to temp) | Near-instant |
| **Distribution** | Simpler (one file) | Requires installer or zip |
| **Debugging** | Harder | Easier (can inspect files) |
| **Antivirus flags** | More frequent false positives | Fewer false positives |
| **Temp disk usage** | Extracts full bundle to `_MEIxxxxxx` on each run | None |

**Recommendation:** Use `--onedir` mode. The one-file mode causes noticeable startup delays and more antivirus false positives. Since we will be creating a proper installer anyway (see Section 4), the single-file convenience is unnecessary. The one-directory output gets wrapped into the installer.

### Hidden Imports for PySide6

PyInstaller's hooks handle most PySide6 imports automatically. However, certain imports may be missed when they are loaded dynamically (via `__import__()`, `importlib.import_module()`, `exec()`, or `eval()`). Common hidden imports needed for PySide6 apps:

```python
hiddenimports = [
    'PySide6.QtSvg',          # If using SVG icons
    'PySide6.QtSvgWidgets',   # If using QSvgWidget
    'PySide6.QtPrintSupport', # If using print dialogs
    'PySide6.QtXml',          # If processing XML
]
```

To diagnose missing imports, build with `--debug=imports` and run the resulting executable to see import errors.

### Including Data Files (JSON, SQLite, Text)

Data files are specified using the `datas` parameter in the `.spec` file or via the `--add-data` command-line flag:

```bash
pyinstaller --add-data "data/templates;data/templates" ^
            --add-data "data/reference;data/reference" ^
            --add-data "data/database.db;data" ^
            my_app.py
```

The format is `source;destination` on Windows (colon-separated on Linux/macOS).

**Accessing bundled data at runtime** requires resolving the correct path, since in a frozen app the working directory differs from development:

```python
import sys
import os

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if getattr(sys, 'frozen', False):
        # Running as a bundled exe
        base_path = sys._MEIPASS  # one-file mode temp dir
        # OR for one-dir mode: base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)
```

**Note on `--onedir` mode:** In one-directory mode, data files are placed alongside the executable. `sys._MEIPASS` still works and points to the directory containing the executable and all extracted files.

### The .spec File Configuration

A complete `.spec` file for our worldbuilding application:

```python
# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files
added_files = [
    ('data/templates/*.json', 'data/templates'),
    ('data/reference/*.txt', 'data/reference'),
    ('data/database.db', 'data'),
    ('assets/icons', 'assets/icons'),
    ('assets/styles', 'assets/styles'),
]

# Exclude heavy Qt modules we do not use
excluded_modules = [
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DAnimation',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtQml',
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtPositioning',
    'PySide6.QtRemoteObjects',
    'PySide6.QtWebSockets',
    'PySide6.QtHttpServer',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # True = one-dir mode
    name='WorldbuildingTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'Qt*.dll',             # Do NOT compress Qt DLLs (causes corruption)
        'pyside6*.pyd',
        'shiboken6*.pyd',
    ],
    console=False,             # No console window (GUI app)
    icon='assets/icons/app.ico',
    version='version_info.txt',  # Optional: Windows version resource
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[
        'Qt*.dll',
        'pyside6*.pyd',
        'shiboken6*.pyd',
    ],
    name='WorldbuildingTool',
)
```

### Common Pitfalls and Solutions

| Problem | Solution |
|---------|----------|
| **"No Qt platform plugin could be initialized"** | Update PyInstaller and hooks (`pip install --upgrade pyinstaller pyinstaller-hooks-contrib`). Ensure PySide6 comes from the virtualenv, not a system install. |
| **System PySide6 vs. virtualenv PySide6** | PyInstaller may pick up system PySide6 instead of virtualenv. Run `pip uninstall pyside6 pyside6_essentials pyside6_addons shiboken6 -y` outside the venv to ensure clean state. |
| **Missing data files at runtime** | Use `sys._MEIPASS` or `os.path.dirname(sys.executable)` to locate bundled files. Test with both frozen and unfrozen execution. |
| **Multiple Qt bindings detected** | PyInstaller 6.x aborts if it finds multiple Qt bindings (PyQt5, PyQt6, PySide2, PySide6). Uninstall all except PySide6. |
| **Antivirus false positives** | More common with `--onefile`. Use `--onedir`, code-sign the executable, and submit to antivirus vendors for whitelisting. |
| **Import errors in frozen app** | Build with `--debug=imports`, run the exe, and add missing modules to `hiddenimports`. |
| **Large bundle size** | See Section 3 for optimization strategies. |

### Build Command

```bash
# First time: generate the .spec file
pyinstaller --name WorldbuildingTool --windowed --icon assets/icons/app.ico main.py

# Subsequent builds: use the .spec file
pyinstaller WorldbuildingTool.spec
```

Output lands in `dist/WorldbuildingTool/`.

---

## 2. Alternative Packagers

### Comparison Matrix

| Feature | PyInstaller | Nuitka | cx_Freeze | Briefcase (BeeWare) |
|---------|-------------|--------|-----------|---------------------|
| **Approach** | Freeze (bundle interpreter + bytecode) | Compile Python to C, then to native binary | Freeze (similar to PyInstaller) | Freeze using embedded Python |
| **PySide6 support** | Excellent (built-in hooks) | Good (`--enable-plugin=pyside6`) | Good (built-in hooks, occasional bugs) | Supported (option 2 in project creation) |
| **Typical bundle size** | 150-300 MB (PySide6) | 100-200 MB (smaller) | 150-300 MB (similar to PyInstaller) | 150-300 MB |
| **Startup time** | Fast (one-dir), slow (one-file) | Fast (native code) | Fast | Fast |
| **Build time** | Fast (seconds to minutes) | Very slow (minutes to hours) | Fast | Moderate |
| **Source protection** | Weak (easy to decompile .pyc) | Strong (compiled to C then machine code) | Weak (similar to PyInstaller) | Weak |
| **Ease of use** | High | Moderate | Moderate | High (for new projects) |
| **Documentation** | Excellent | Good | Good | Good |
| **Community** | Very large | Growing | Moderate | Moderate |
| **Latest version** | 6.18.0 (Jan 2026) | 2.6.x | 8.5.3 | 0.3.26 |

### PyInstaller (Recommended)

The most popular and battle-tested option. Extensive documentation, largest community, and the most up-to-date PySide6 hooks. Best for our use case due to simplicity, speed of iteration, and proven track record.

**Pros:** Fast builds, excellent PySide6 support, large ecosystem, well-documented.
**Cons:** Larger bundles, easy to decompile, occasional antivirus false positives.

### Nuitka

Compiles Python to C code, producing genuinely native executables. Offers better source code protection and somewhat smaller bundle sizes. The `--enable-plugin=pyside6` flag handles Qt integration.

```bash
nuitka --onefile --enable-plugin=pyside6 --disable-console ^
       --windows-icon-from-ico=app.ico --output-dir=dist main.py
```

**Pros:** Smaller output, better performance, superior source protection, fewer antivirus false positives.
**Cons:** Very slow build times (can take 30+ minutes for a PySide6 app), steeper learning curve, more complex debugging. The commercial version (Nuitka Commercial) offers additional optimizations.

### cx_Freeze

Similar to PyInstaller but with a `setup.py`-based configuration. Version 8.5.3 is current. Had a notable PySide6 bug in version 8.1.0 where the hook looked for a renamed file (`debug.py` vs. `_debug.py`), fixed in 8.2.0+.

```python
from cx_Freeze import setup, Executable

build_exe_options = {
    "zip_include_packages": ["encodings", "PySide6", "shiboken6"],
    "excludes": ["PySide6.QtWebEngine", "PySide6.QtQuick3D"],
}

setup(
    name="WorldbuildingTool",
    version="1.0",
    options={"build_exe": build_exe_options},
    executables=[Executable("main.py", base="gui", icon="app.ico")],
)
```

**Pros:** Mature, well-maintained, `setup.py` integration familiar to Python developers.
**Cons:** Slightly less PySide6 community support than PyInstaller, occasional hook bugs with new PySide6 releases.

### Briefcase (BeeWare)

Oriented toward creating native application packages. Uses the official Python embeddable package and WiX Toolset for MSI creation on Windows. Supports PySide6 as a GUI framework option.

```bash
briefcase create windows
briefcase build windows
briefcase package windows        # Creates MSI installer
briefcase package windows -p zip # Creates ZIP archive
```

**Pros:** Native installer output (MSI), cross-platform project structure, code signing support built in.
**Cons:** Known issue with PySide6 on Windows -- deeply nested PySide6 file paths can exceed the 260-character Windows path limit, causing WiX packaging failures. Less flexible for existing projects (designed for new Briefcase-structured projects). Smaller community.

### Recommendation

**Use PyInstaller** for this project. It has the best PySide6 support, fastest iteration cycle, largest community, and extensive documentation. If source code protection becomes a priority in the future, consider migrating to Nuitka for release builds while keeping PyInstaller for development testing.

---

## 3. Bundle Size Optimization

### The Problem

A typical PySide6 application bundled with PyInstaller produces a 150-300 MB output directory. The Qt framework includes many modules (WebEngine, 3D, Multimedia, QML) that a Widgets-based app does not need.

### Strategy 1: Install Only PySide6-Essentials

The PySide6 package is split into two wheels:
- **`PySide6-Essentials`** -- Core modules (QtCore, QtGui, QtWidgets, QtSvg, etc.)
- **`PySide6-Addons`** -- Extra modules (QtWebEngine, Qt3D, QtMultimedia, QtQuick, etc.)

The top-level `PySide6` package is a convenience wrapper that installs both. For our app:

```bash
pip uninstall PySide6 PySide6-Addons PySide6-Essentials shiboken6 -y
pip install PySide6-Essentials
```

This alone can reduce the bundle by 50-100 MB by not including add-on modules at all.

### Strategy 2: Exclude Unused Qt Modules in PyInstaller

In the `.spec` file, use the `excludes` list in `Analysis()`:

```python
excludes = [
    # WebEngine is the biggest offender (~150 MB on its own)
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
    # 3D modules
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DExtras', 'PySide6.Qt3DAnimation',
    # Multimedia
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    # QML/Quick (we use Widgets, not QML)
    'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQml',
    'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2',
    # Other unused modules
    'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtSensors',
    'PySide6.QtSerialPort', 'PySide6.QtPositioning',
    'PySide6.QtRemoteObjects', 'PySide6.QtWebSockets',
    'PySide6.QtHttpServer', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtDesigner', 'PySide6.QtHelp',
    # Also exclude the designer plugin that drags in WebEngine
    'PySide6.QtUiTools',
]
```

**Important:** The `QtUiTools` hook can trigger collection of designer plugins including `qwebengineview`, which pulls in the entire QtWebEngine (~150-175 MB on Linux, ~80 MB on Windows). Exclude `QtUiTools` if you do not use `.ui` files at runtime.

### Strategy 3: UPX Compression (Windows Only)

UPX compresses individual binaries by 50-70%. However, it **must not** be applied to Qt/PySide6 DLLs, which can become corrupted (especially those with Control Flow Guard enabled).

```python
# In the .spec file
exe = EXE(
    ...
    upx=True,
    upx_exclude=[
        'Qt*.dll',
        'pyside6*.pyd',
        'shiboken6*.pyd',
    ],
)
```

Realistic savings: 20-30% reduction on the non-Qt portion of the bundle. Some antivirus tools may flag UPX-compressed executables as suspicious.

### Strategy 4: pyside6-deploy Tool

Qt provides an official deployment tool that analyzes your application and generates a deployment configuration:

```bash
pyside6-deploy main.py
```

This creates a `pysidedeploy.spec` configuration file where you can:
- Set `modules` to a comma-separated list of only the Qt modules your app uses
- Set `excluded_qml_plugins` to remove unused QML plugins
- Control Nuitka options (pyside6-deploy uses Nuitka under the hood)

The tool auto-detects which modules are used by static analysis of your imports.

### Strategy 5: Post-Build Cleanup Script

After PyInstaller builds, remove known unnecessary files from the output directory:

```python
# cleanup_dist.py
import os
import glob
import shutil

dist_dir = 'dist/WorldbuildingTool'

# Patterns to remove
remove_patterns = [
    'Qt6WebEngine*',
    'Qt6Quick*',
    'Qt6Qml*',
    'Qt63D*',
    'Qt6Multimedia*',
    'Qt6Bluetooth*',
    'Qt6Nfc*',
    'Qt6Sensors*',
    'Qt6SerialPort*',
    'Qt6Pdf*',
    'opengl32sw.dll',           # Software OpenGL renderer (large, rarely needed)
    'd3dcompiler_47.dll',       # DirectX compiler (only needed for QtQuick)
    'PySide6/translations/*',   # Translation files (if single-language)
]

for pattern in remove_patterns:
    for path in glob.glob(os.path.join(dist_dir, '**', pattern), recursive=True):
        if os.path.isfile(path):
            os.remove(path)
            print(f'Removed: {path}')
        elif os.path.isdir(path):
            shutil.rmtree(path)
            print(f'Removed dir: {path}')
```

### Strategy 6: Virtual Environment (Most Important)

Always build from a clean virtual environment that contains **only** the packages your app needs. This prevents PyInstaller from bundling unrelated packages.

```bash
python -m venv build_env
build_env\Scripts\activate
pip install PySide6-Essentials pyinstaller
pip install -r requirements.txt  # Only your app's actual dependencies
pyinstaller WorldbuildingTool.spec
```

### Modules We Actually Need

For a Widgets-based worldbuilding tool with SVG icons:

| Module | Needed | Why |
|--------|--------|-----|
| `QtCore` | Yes | Signals/slots, file I/O, settings |
| `QtGui` | Yes | Fonts, colors, images, painting |
| `QtWidgets` | Yes | All UI widgets |
| `QtSvg` | Yes | SVG icon rendering |
| `QtSvgWidgets` | Maybe | Only if using QSvgWidget directly |
| `QtPrintSupport` | Maybe | Only if printing/export-to-PDF is needed |
| `QtSql` | Maybe | If using Qt's SQL classes (vs. raw sqlite3) |
| Everything else | No | Exclude aggressively |

### Expected Size After Optimization

| Stage | Approximate Size |
|-------|-----------------|
| Naive PyInstaller build (full PySide6) | 250-300 MB |
| Using PySide6-Essentials only | 150-200 MB |
| + Excluding unused modules | 100-150 MB |
| + Post-build cleanup | 80-120 MB |
| + UPX on non-Qt binaries | 70-100 MB |
| Compressed in installer (LZMA) | 35-55 MB |

---

## 4. Installer Creation

After creating the PyInstaller one-directory bundle, wrap it in a proper Windows installer for end users.

### Inno Setup (Recommended)

**Website:** https://jrsoftware.org/isinfo.php
**License:** Free, open source
**Output:** EXE installer

The most popular choice for Python application installers. Pascal-based scripting, built-in wizard, handles desktop shortcuts, Start Menu entries, uninstaller, and file associations.

```iss
; WorldbuildingTool.iss -- Inno Setup Script

[Setup]
AppId={{UNIQUE-GUID-HERE}
AppName=Worldbuilding Tool
AppVersion=1.0.0
AppPublisher=Your Name
AppPublisherURL=https://github.com/yourname/worldbuilding-tool
DefaultDirName={autopf}\WorldbuildingTool
DefaultGroupName=Worldbuilding Tool
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=WorldbuildingTool-Setup-1.0.0
Compression=lzma2/ultra64
SolidCompression=yes
SetupIconFile=assets\icons\app.ico
UninstallDisplayIcon={app}\WorldbuildingTool.exe
WizardStyle=modern
PrivilegesRequired=lowest
; PrivilegesRequired=lowest allows install without admin rights

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Bundle the entire PyInstaller output directory
Source: "dist\WorldbuildingTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Worldbuilding Tool"; Filename: "{app}\WorldbuildingTool.exe"
Name: "{group}\{cm:UninstallProgram,Worldbuilding Tool}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Worldbuilding Tool"; Filename: "{app}\WorldbuildingTool.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WorldbuildingTool.exe"; Description: "{cm:LaunchProgram,Worldbuilding Tool}"; Flags: nowait postinstall skipifsilent
```

**Key features:**
- LZMA2 compression reduces a 100 MB bundle to ~40 MB installer
- `PrivilegesRequired=lowest` allows per-user install without admin rights
- Built-in uninstaller registered in Windows "Apps & Features"
- Silent install support: `WorldbuildingTool-Setup.exe /SILENT`
- Digital signature support via `SignTool` directive

### NSIS (Nullsoft Scriptable Install System)

**Website:** https://nsis.sourceforge.io/
**License:** Free, open source
**Output:** EXE installer

More customizable than Inno Setup but with a steeper learning curve. The scripting language is assembly-like. Smallest installer overhead (~34 KB vs. Inno's ~200-300 KB).

```nsis
; WorldbuildingTool.nsi

!include "MUI2.nsh"

Name "Worldbuilding Tool"
OutFile "WorldbuildingTool-Setup-1.0.0.exe"
InstallDir "$LOCALAPPDATA\WorldbuildingTool"
RequestExecutionLevel user

; Modern UI pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath "$INSTDIR"
    File /r "dist\WorldbuildingTool\*.*"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\Worldbuilding Tool"
    CreateShortcut "$SMPROGRAMS\Worldbuilding Tool\Worldbuilding Tool.lnk" "$INSTDIR\WorldbuildingTool.exe"
    CreateShortcut "$SMPROGRAMS\Worldbuilding Tool\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Desktop shortcut
    CreateShortcut "$DESKTOP\Worldbuilding Tool.lnk" "$INSTDIR\WorldbuildingTool.exe"

    ; Registry for Add/Remove Programs
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorldbuildingTool" "DisplayName" "Worldbuilding Tool"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorldbuildingTool" "UninstallString" "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\Worldbuilding Tool"
    Delete "$DESKTOP\Worldbuilding Tool.lnk"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\WorldbuildingTool"
SectionEnd
```

**Key features:**
- Extremely small overhead (~34 KB)
- Vast plugin ecosystem
- Fine-grained control over every aspect of installation
- More complex scripting than Inno Setup

### InstallForge

**Website:** https://installforge.net/
**License:** Free
**Output:** EXE installer

GUI-based installer builder. No scripting required -- you configure everything through a visual interface. Good for developers who prefer not to write installer scripts.

**Key features:**
- Entirely GUI-driven configuration
- Desktop shortcut, Start Menu, uninstaller support
- Serial number / license key validation
- No scripting language to learn

**Drawbacks:**
- Less flexible than Inno Setup or NSIS for custom logic
- Smaller community and fewer resources

### WiX Toolset

**Website:** https://wixtoolset.org/
**License:** Free, open source
**Output:** MSI installer

Produces native Windows Installer (MSI) packages. Best suited for enterprise deployments where Group Policy (GPO) or SCCM distribution is needed. XML-based configuration with a steep learning curve.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="Worldbuilding Tool"
           Version="1.0.0"
           Manufacturer="Your Name"
           UpgradeCode="PUT-GUID-HERE">

    <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
    <MediaTemplate EmbedCab="yes" />

    <Feature Id="Complete" Level="1">
      <ComponentGroupRef Id="AppFiles" />
    </Feature>

    <StandardDirectory Id="LocalAppDataFolder">
      <Directory Id="INSTALLFOLDER" Name="WorldbuildingTool">
        <ComponentGroup Id="AppFiles" Directory="INSTALLFOLDER">
          <!-- Populated by heat.exe harvesting tool -->
        </ComponentGroup>
      </Directory>
    </StandardDirectory>
  </Package>
</Wix>
```

**Key features:**
- Native MSI format (preferred by enterprise IT departments)
- Integrates with Visual Studio
- Supports Windows services, drivers, registry, and complex installation scenarios
- Handles upgrades and patches natively

**Drawbacks:**
- Steep learning curve
- XML-heavy configuration
- Overkill for consumer applications
- Known issue: paths > 260 characters cause failures (affects PySide6 with deep directory structures)

### Installer Recommendation

**Use Inno Setup.** It offers the best balance of simplicity, features, and community support for our use case. The LZMA2 compression significantly reduces download size, it handles shortcuts and uninstallation cleanly, and the scripting language is readable. Only consider WiX if enterprise MSI deployment becomes a requirement.

---

## 5. Auto-Updates

### Approach 1: GitHub Releases API (Recommended for Open Source)

Check for new versions by querying the GitHub Releases API. This is simple, requires no server infrastructure, and integrates with the existing development workflow.

```python
import json
import urllib.request
from packaging.version import Version

CURRENT_VERSION = "1.0.0"
GITHUB_API_URL = "https://api.github.com/repos/yourname/worldbuilding-tool/releases/latest"

def check_for_updates():
    """Check GitHub for a newer release. Returns (new_version, download_url) or None."""
    try:
        req = urllib.request.Request(GITHUB_API_URL)
        req.add_header('Accept', 'application/vnd.github.v3+json')
        req.add_header('User-Agent', 'WorldbuildingTool-UpdateChecker')

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())

        latest_version = data['tag_name'].lstrip('v')
        if Version(latest_version) > Version(CURRENT_VERSION):
            # Find the installer asset
            for asset in data.get('assets', []):
                if asset['name'].endswith('-Setup.exe'):
                    return latest_version, asset['browser_download_url']
        return None
    except Exception:
        return None  # Silently fail -- don't interrupt the user
```

**Update flow for end users:**

1. On startup (or periodically), the app calls `check_for_updates()` in a background thread.
2. If an update is found, show a non-intrusive notification: "Version X.Y.Z is available. Download now?"
3. If the user accepts, open the download URL in the default browser, or download the installer to a temp directory and launch it.
4. The new installer handles replacing the old version (Inno Setup's `AppId` ensures proper upgrade).

### Approach 2: tufup (Secure Auto-Updates)

[tufup](https://github.com/dennisvang/tufup) is built on The Update Framework (TUF), providing cryptographically secure updates. It supports:

- Full application archive updates
- Differential/patch updates (binary diffs to reduce download size)
- Signed metadata to prevent tampering
- Works with PyInstaller-bundled apps

```python
# Integration sketch
from tufup.client import Client

client = Client(
    app_name='WorldbuildingTool',
    current_version='1.0.0',
    metadata_dir=metadata_path,
    metadata_base_url='https://yourserver.com/updates/metadata/',
    target_dir=target_path,
    target_base_url='https://yourserver.com/updates/targets/',
)

# Check and apply update
if client.check_for_updates():
    client.download_and_apply_update()
```

**Pros:** Secure, supports patches (small downloads), production-grade.
**Cons:** Requires hosting update metadata, more complex setup, additional server infrastructure.

### Approach 3: updater4pyi (Lightweight, PyInstaller-Native)

[updater4pyi](https://pypi.org/project/updater4pyi/) is designed specifically for PyInstaller applications. Supports GitHub Releases as an update source. Works with both one-file and one-dir modes.

### Approach 4: Simple Self-Update via Download

For the simplest possible approach:

```python
import subprocess
import sys
import tempfile
import urllib.request

def download_and_run_installer(url):
    """Download the new installer and run it, then exit the current app."""
    temp_dir = tempfile.mkdtemp()
    installer_path = os.path.join(temp_dir, 'WorldbuildingTool-Setup.exe')

    urllib.request.urlretrieve(url, installer_path)

    # Launch the installer and exit the current app
    subprocess.Popen([installer_path, '/SILENT'])
    sys.exit(0)
```

### Recommendation

Start with **Approach 1 (GitHub Releases API)** for version checking and notification. Direct the user to download the new installer from the GitHub Releases page or auto-download it. This requires zero server infrastructure and is trivial to implement. Migrate to **tufup** if differential updates or higher security becomes important.

---

## 6. Data File Management

### The Separation Principle

Application files (executables, libraries, bundled resources) must be kept separate from user data (created entities, saved state, customizations). This ensures that:

1. Upgrades do not overwrite user data
2. Uninstallation can optionally preserve user data
3. User data can be backed up independently
4. The application directory can be read-only (no admin rights needed for normal use)

### Where to Store What

| Data Type | Location | Path |
|-----------|----------|------|
| **Application binaries** | Program Files or LocalAppData install | `{app}\` |
| **Bundled templates** (read-only defaults) | Inside app directory | `{app}\data\templates\` |
| **Bundled reference files** (read-only) | Inside app directory | `{app}\data\reference\` |
| **User-created entities** | LOCALAPPDATA | `%LOCALAPPDATA%\WorldbuildingTool\entities\` |
| **User state/settings** (`state.json`) | LOCALAPPDATA | `%LOCALAPPDATA%\WorldbuildingTool\state.json` |
| **User database** | LOCALAPPDATA | `%LOCALAPPDATA%\WorldbuildingTool\database.db` |
| **Logs** | LOCALAPPDATA | `%LOCALAPPDATA%\WorldbuildingTool\logs\` |
| **Cache** | LOCALAPPDATA | `%LOCALAPPDATA%\WorldbuildingTool\cache\` |

### Using platformdirs

The [platformdirs](https://github.com/tox-dev/platformdirs) library (successor to `appdirs`) provides cross-platform directory resolution:

```python
from platformdirs import user_data_dir, user_config_dir, user_log_dir, user_cache_dir

APP_NAME = "WorldbuildingTool"
APP_AUTHOR = "YourName"

# On Windows, these resolve to:
# %LOCALAPPDATA%\YourName\WorldbuildingTool
data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
config_dir = user_config_dir(APP_NAME, APP_AUTHOR)
log_dir = user_log_dir(APP_NAME, APP_AUTHOR)
cache_dir = user_cache_dir(APP_NAME, APP_AUTHOR)
```

**Why LOCALAPPDATA over APPDATA (Roaming)?** Roaming AppData is synced across machines in enterprise domain environments. A large SQLite database or many entity files would slow down domain logins. Use Local unless you specifically need roaming.

### First-Run Setup

On first launch, copy default templates and initialize the database:

```python
import os
import shutil

def initialize_user_data():
    """Copy default templates and create initial database on first run."""
    data_dir = user_data_dir(APP_NAME, APP_AUTHOR)

    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

        # Copy default templates from the bundled app directory
        bundled_templates = get_resource_path('data/templates')
        user_templates = os.path.join(data_dir, 'templates')
        shutil.copytree(bundled_templates, user_templates)

        # Copy default database
        bundled_db = get_resource_path('data/database.db')
        user_db = os.path.join(data_dir, 'database.db')
        shutil.copy2(bundled_db, user_db)

        # Create initial state
        state = {
            "version": CURRENT_VERSION,
            "first_run": True,
            "created": datetime.now().isoformat(),
        }
        with open(os.path.join(data_dir, 'state.json'), 'w') as f:
            json.dump(state, f, indent=2)
```

### Handling Upgrades Without Losing User Data

When the application updates, the installer replaces files in the application directory but never touches `%LOCALAPPDATA%\WorldbuildingTool\`. On first launch after an upgrade:

```python
def handle_upgrade():
    """Check if the app version is newer than the user data version and migrate."""
    data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
    state_path = os.path.join(data_dir, 'state.json')

    if not os.path.exists(state_path):
        initialize_user_data()
        return

    with open(state_path, 'r') as f:
        state = json.load(f)

    data_version = Version(state.get('version', '0.0.0'))
    app_version = Version(CURRENT_VERSION)

    if data_version < app_version:
        # Run migrations
        if data_version < Version('1.1.0'):
            migrate_to_1_1_0(data_dir)
        if data_version < Version('1.2.0'):
            migrate_to_1_2_0(data_dir)

        # Copy any new templates that did not exist before
        sync_new_templates(data_dir)

        # Update the stored version
        state['version'] = CURRENT_VERSION
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)

def sync_new_templates(data_dir):
    """Copy new bundled templates to user data, without overwriting existing ones."""
    bundled = get_resource_path('data/templates')
    user_templates = os.path.join(data_dir, 'templates')

    for filename in os.listdir(bundled):
        dest = os.path.join(user_templates, filename)
        if not os.path.exists(dest):
            shutil.copy2(os.path.join(bundled, filename), dest)
```

### Database Migration Strategy

For SQLite schema changes across versions:

```python
def migrate_database(db_path, from_version, to_version):
    """Apply incremental schema migrations."""
    import sqlite3
    conn = sqlite3.connect(db_path)

    # Store schema version in the database itself
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version TEXT)")

    migrations = {
        '1.1.0': [
            "ALTER TABLE entities ADD COLUMN tags TEXT DEFAULT ''",
            "CREATE INDEX idx_entities_tags ON entities(tags)",
        ],
        '1.2.0': [
            "ALTER TABLE entities ADD COLUMN last_modified TEXT",
        ],
    }

    for version, statements in sorted(migrations.items()):
        if Version(from_version) < Version(version) <= Version(to_version):
            for sql in statements:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # Column/index may already exist
    conn.commit()
    conn.close()
```

### Inno Setup: Preserve User Data on Uninstall

In the Inno Setup script, you can prompt the user:

```iss
[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if MsgBox('Do you want to remove your saved data (entities, settings)?',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\WorldbuildingTool'), True, True, True);
    end;
  end;
end;
```

---

## 7. Code Signing

### The Problem

Unsigned Windows executables trigger SmartScreen warnings ("Windows protected your PC -- Microsoft Defender SmartScreen prevented an unrecognized app from starting"). This frightens non-technical users and can prevent them from running the application entirely.

### Certificate Types and Costs (2025-2026)

| Option | Annual Cost | SmartScreen Behavior | Requirements |
|--------|-------------|---------------------|--------------|
| **No signing** | Free | Full SmartScreen warning on every run | None |
| **OV (Organization Validation)** | $200-400/year | Builds reputation gradually over months | Registered business or verified identity |
| **EV (Extended Validation)** | $250-500+/year | Builds reputation gradually (changed March 2024) | Registered business (LLC minimum), hardware token |
| **Certum (open-source discount)** | ~$75/year (first year) | Builds reputation gradually | Open-source project proof |
| **Azure Trusted Signing** | $9.99/month (~$120/year) | Immediate SmartScreen trust | US/Canada, 3+ years verifiable business history |
| **Self-signed** | Free | No SmartScreen benefit (still shows warnings) | None |

### Important Changes (2024)

As of March 2024, Microsoft changed SmartScreen behavior: EV certificates **no longer** provide instant reputation. Both OV and EV certificates now build reputation organically through download volume and user installation patterns. This eliminated the primary advantage of expensive EV certificates for SmartScreen purposes.

### Hardware Token Requirement

Since June 2023, the CA/Browser Forum requires all code signing private keys to be stored on a hardware security module (HSM) meeting FIPS 140 Level 2 or Common Criteria EAL 4+. This means:

- You will receive a USB hardware token (e.g., SafeNet/Thales eToken) with your certificate
- Signing must be done on a machine with the token physically plugged in
- Cloud-based signing services (like SSL.com's eSigner or Azure Trusted Signing) handle this requirement server-side

### Azure Trusted Signing (Best Value)

Microsoft's own service at $9.99/month provides:
- Immediate SmartScreen trust (no reputation building period)
- No hardware token needed (cloud-based HSM)
- Integration with GitHub Actions for CI/CD signing
- Available to US and Canada organizations with 3+ years history, and individual US/Canada developers

### MSIX as a SmartScreen Alternative

Packaging your application as MSIX (Microsoft's modern app package format) avoids SmartScreen prompts entirely, even without code signing. This can be combined with PyInstaller:

1. Bundle with PyInstaller into a directory
2. Package the directory as MSIX using Microsoft's MSIX Packaging Tool
3. Distribute the `.msix` file or publish to the Microsoft Store

### Signing with Inno Setup

```iss
[Setup]
SignTool=signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a $f
SignedUninstaller=yes
```

### Recommendation for This Project

For an open-source or small-scale project:

1. **Start without signing.** Include instructions in the README for bypassing SmartScreen ("Click 'More info' then 'Run anyway'").
2. **When the user base grows**, get a Certum open-source certificate (~$75/year) or an OV certificate (~$200-400/year).
3. **If budget allows and you are US/Canada-based**, use Azure Trusted Signing ($120/year) for immediate SmartScreen trust.
4. **Do not bother with EV certificates** -- since March 2024, they provide no SmartScreen advantage over OV.

---

## 8. Prerequisites & Runtime Dependencies

### Does the User Need Python Installed?

**No.** PyInstaller bundles the Python interpreter (specifically, `python3x.dll` and the standard library) into the output directory. The end user does not need Python installed at all. This is the entire point of using PyInstaller.

### Does the User Need Any Visual C++ Redistributable?

**Usually no** for modern Windows (10/11). The Python interpreter and PySide6/Qt libraries are linked against the Universal C Runtime (UCRT), which is included in Windows 10 and later. For Windows 7/8.1 (rare in 2026), the user might need the Visual C++ 2015-2022 Redistributable.

If you want to be safe, you can bundle the VC++ redistributable installer and run it silently during installation:

```iss
; Inno Setup: Install VC++ Redistributable if needed
[Files]
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Run]
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/quiet /norestart"; StatusMsg: "Installing Visual C++ Runtime..."; Check: VCRedistNeedsInstall
```

### Does Claude Code CLI Need to Be Installed Separately?

If the application uses Claude Code CLI as an external process (invoked via `subprocess`), then **yes**, it must be installed separately on the user's machine. The application should:

1. **Detect at startup** whether the Claude CLI is available:

```python
import shutil
import subprocess

def check_claude_cli():
    """Check if Claude Code CLI is available and return version info."""
    claude_path = shutil.which('claude')
    if claude_path is None:
        return None, "Claude Code CLI not found in PATH"

    try:
        result = subprocess.run(
            ['claude', '--version'],
            capture_output=True, text=True, timeout=10
        )
        return claude_path, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None, "Claude Code CLI not responding"
```

2. **Show a friendly setup dialog** on first run if Claude CLI is missing:

```python
from PySide6.QtWidgets import QMessageBox

def prompt_claude_install(parent):
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Setup Required")
    msg.setText("Claude Code CLI is not installed.")
    msg.setInformativeText(
        "Some features require the Claude Code CLI.\n\n"
        "Install it with: npm install -g @anthropic-ai/claude-code\n\n"
        "You can use the app without it, but AI-powered features "
        "will be unavailable."
    )
    msg.addButton("Open Install Instructions", QMessageBox.ActionRole)
    msg.addButton("Continue Without Claude", QMessageBox.RejectRole)
    return msg.exec()
```

3. **Allow the app to function in a degraded mode** without Claude CLI, disabling only the features that require it. Never block the entire application.

### Node.js / npm Dependency

If Claude Code CLI requires Node.js and npm, the user needs those installed as well. The application should check for this:

```python
def check_prerequisites():
    """Check all external prerequisites and return a status report."""
    prereqs = {}

    # Check Node.js
    node_path = shutil.which('node')
    prereqs['nodejs'] = {
        'installed': node_path is not None,
        'path': node_path,
        'install_url': 'https://nodejs.org/',
    }

    # Check Claude CLI
    claude_path = shutil.which('claude')
    prereqs['claude_cli'] = {
        'installed': claude_path is not None,
        'path': claude_path,
        'install_cmd': 'npm install -g @anthropic-ai/claude-code',
    }

    return prereqs
```

### Summary of What Gets Bundled vs. What the User Installs

| Component | Bundled in Installer? | User Must Install? |
|-----------|----------------------|-------------------|
| Python interpreter | Yes (via PyInstaller) | No |
| PySide6 / Qt libraries | Yes (via PyInstaller) | No |
| Application code | Yes | No |
| JSON templates | Yes | No |
| SQLite database (default) | Yes | No |
| Reference text files | Yes | No |
| Visual C++ Runtime | Usually not needed (Win 10/11) | Rarely |
| Claude Code CLI | No | Yes (for AI features) |
| Node.js / npm | No | Yes (if Claude CLI needed) |

---

## Summary of Recommendations

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| **Packager** | PyInstaller | Best PySide6 support, fastest builds, largest community |
| **Mode** | `--onedir` | Faster startup, fewer AV issues, wrapped in installer anyway |
| **Size optimization** | PySide6-Essentials + exclude modules + post-build cleanup | Can reduce from 300 MB to ~80-100 MB before compression |
| **Installer** | Inno Setup | Free, simple, LZMA compression, excellent feature set |
| **User data location** | `%LOCALAPPDATA%\WorldbuildingTool\` via platformdirs | Standard Windows convention, survives upgrades |
| **Auto-updates** | GitHub Releases API + notification | Zero infrastructure, simple to implement |
| **Code signing** | Start unsigned, add Certum/Azure Trusted Signing when ready | Cost-effective, SmartScreen reputation builds over time |
| **Prerequisites** | Bundle everything except Claude CLI | Detect and prompt for Claude CLI gracefully |

---

## References

- [PythonGUIs: Packaging PySide6 with PyInstaller & InstallForge](https://www.pythonguis.com/tutorials/packaging-pyside6-applications-windows-pyinstaller-installforge/)
- [Qt Official: PyInstaller Deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)
- [Qt Official: Nuitka Deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-nuitka.html)
- [Qt Official: pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
- [PyInstaller Documentation v6.18.0](https://pyinstaller.org/en/stable/)
- [PyInstaller Spec Files](https://pyinstaller.org/en/stable/spec-files.html)
- [Nuitka vs PyInstaller: Real Differences](https://krrt7.dev/en/blog/nuitka-vs-pyinstaller)
- [Erriez/pyside6-nuitka-deployment (GitHub)](https://github.com/Erriez/pyside6-nuitka-deployment)
- [cx_Freeze Documentation v8.5](https://cx-freeze.readthedocs.io/en/stable/)
- [cx_Freeze PySide6 Bug Report](https://brainsteam.co.uk/2025/4/18/cxfreeze-810-pyside-broken/)
- [Briefcase Documentation v0.3.25](https://briefcase.beeware.org/en/stable/)
- [PyInstaller PySide6 Issue #6447 (Qt Module Size)](https://github.com/pyinstaller/pyinstaller/issues/6447)
- [tufup: Secure Auto-Updates for Python Apps](https://github.com/dennisvang/tufup)
- [updater4pyi on PyPI](https://pypi.org/project/updater4pyi/)
- [platformdirs (GitHub)](https://github.com/tox-dev/platformdirs)
- [Inno Setup](https://jrsoftware.org/isinfo.php)
- [NSIS](https://nsis.sourceforge.io/)
- [WiX Toolset](https://wixtoolset.org/)
- [SSL Insights: OV vs EV Code Signing](https://sslinsights.com/best-code-signing-certificate-windows-applications/)
- [Azure Trusted Signing Setup (Rick Strahl)](https://weblog.west-wind.com/posts/2025/Jul/20/Fighting-through-Setting-up-Microsoft-Trusted-Signing)
- [MSIX Packaging with PyInstaller](https://82phil.github.io/python/2025/04/24/msix_pyinstaller.html)
- [UPX with PyInstaller (CodersLegacy)](https://coderslegacy.com/python/pyinstaller-upx/)
- [DeepWiki: PySide6 Packaging & Deployment](https://deepwiki.com/muziing/PySide6-Code-Tutorial/3.7-packaging-and-deployment)
- [Sparx Engineering: PyInstaller vs Nuitka vs cx_Freeze](https://sparxeng.com/blog/software/python-standalone-executable-generators-pyinstaller-nuitka-cx-freeze)
