"""
build_release.py -- Build automation for Worldbuilding Interactive Program.

Steps:
    1. Create/activate virtual environment
    2. Install dependencies
    3. Run tests
    4. Build with PyInstaller
    5. Clean up unnecessary files from dist
    6. Run Inno Setup installer (if available)
    7. Report results

Usage::

    python build_release.py
    python build_release.py --skip-tests
    python build_release.py --skip-venv
    python build_release.py --clean
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(ROOT, ".build-venv")
DIST_DIR = os.path.join(ROOT, "dist")
BUILD_DIR = os.path.join(ROOT, "build")
APP_DIR = os.path.join(DIST_DIR, "WorldbuildingApp")


def run(cmd: list[str], cwd: str = ROOT, check: bool = True) -> int:
    """Run a command and print output."""
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        print(f"FAILED: {' '.join(cmd)} (exit {result.returncode})")
        sys.exit(result.returncode)
    return result.returncode


def get_python(use_venv: bool) -> str:
    """Return the Python executable path."""
    if use_venv:
        if sys.platform == "win32":
            return os.path.join(VENV_DIR, "Scripts", "python.exe")
        return os.path.join(VENV_DIR, "bin", "python")
    return sys.executable


def _safe_rmtree(path: str, description: str = "") -> None:
    """Remove a directory tree with error handling."""
    label = description or path
    try:
        shutil.rmtree(path)
    except PermissionError:
        print(f"  WARNING: Permission denied removing {label}. "
              f"Close any programs using files in this directory and retry.")
    except OSError as e:
        print(f"  WARNING: Could not remove {label}: {e}")


def step_venv(python: str) -> None:
    """Create virtual environment and install dependencies."""
    if not os.path.isdir(VENV_DIR):
        print("\n=== Creating virtual environment ===")
        run([sys.executable, "-m", "venv", VENV_DIR])

    print("\n=== Installing dependencies ===")
    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    run([python, "-m", "pip", "install", "-r", "requirements.txt"])
    run([python, "-m", "pip", "install", "-r", "requirements-dev.txt"])
    run([python, "-m", "pip", "install", "pyinstaller>=6.0"])


def step_test(python: str) -> None:
    """Run the test suite."""
    print("\n=== Running tests ===")
    run([python, "-m", "pytest", "tests/", "-q", "--tb=short"])


def step_build(python: str) -> None:
    """Build with PyInstaller."""
    print("\n=== Building with PyInstaller ===")

    # Clean previous build
    for d in [BUILD_DIR, APP_DIR]:
        if os.path.isdir(d):
            _safe_rmtree(d, os.path.basename(d))

    run([python, "-m", "PyInstaller", "worldbuilding.spec", "--noconfirm"])


def step_cleanup() -> None:
    """Remove unnecessary files from the dist to reduce size."""
    print("\n=== Cleaning up dist ===")

    if not os.path.isdir(APP_DIR):
        print("No app dir found, skipping cleanup")
        return

    # Remove unnecessary Qt translations, examples, etc.
    patterns_to_remove = [
        os.path.join(APP_DIR, "PySide6", "translations"),
        os.path.join(APP_DIR, "PySide6", "examples"),
    ]
    for path in patterns_to_remove:
        if os.path.isdir(path):
            _safe_rmtree(path, os.path.relpath(path, ROOT))
            print(f"  Removed: {path}")

    # Report size
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)

    size_mb = total_size / (1024 * 1024)
    print(f"\n  Total dist size: {size_mb:.1f} MB")


def step_installer() -> None:
    """Run Inno Setup compiler if available on PATH."""
    print("\n=== Building installer ===")
    iscc = shutil.which("iscc")
    if iscc is None:
        print("  ISCC not found on PATH, skipping installer build.")
        print("  Install Inno Setup and ensure iscc.exe is on your PATH to build the installer.")
        return

    iss_file = os.path.join(ROOT, "installer.iss")
    if not os.path.isfile(iss_file):
        print(f"  installer.iss not found at {iss_file}, skipping.")
        return

    run([iscc, iss_file])
    print("  Installer built successfully.")


def step_clean() -> None:
    """Remove the build virtual environment."""
    print("\n=== Cleaning build environment ===")
    if os.path.isdir(VENV_DIR):
        _safe_rmtree(VENV_DIR, ".build-venv")
        print(f"  Removed {VENV_DIR}")
    else:
        print("  No .build-venv to clean.")

    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.isdir(d):
            _safe_rmtree(d, os.path.basename(d))
            print(f"  Removed {d}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Worldbuilding Interactive Program")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument("--skip-venv", action="store_true", help="Use current Python instead of venv")
    parser.add_argument("--clean", action="store_true", help="Remove .build-venv and build artifacts, then exit")
    args = parser.parse_args()

    if args.clean:
        step_clean()
        return

    use_venv = not args.skip_venv
    python = get_python(use_venv)

    print("=" * 60)
    print("  Worldbuilding Interactive Program - Build Release")
    print("=" * 60)

    if use_venv:
        step_venv(python)

    if not args.skip_tests:
        step_test(python)

    step_build(python)
    step_cleanup()
    step_installer()

    # Clean up build dir
    if os.path.isdir(BUILD_DIR):
        _safe_rmtree(BUILD_DIR, "build")

    print("\n" + "=" * 60)
    print("  BUILD COMPLETE")
    if os.path.isdir(APP_DIR):
        print(f"  Output: {APP_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
