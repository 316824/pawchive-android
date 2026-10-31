"""Check Android wheel/APK versions and native architecture without extracting them.

This is a packaging check, not a replacement for launching on an Android device.
Only Python's standard library is required; no signing keys or network are used.
"""
from __future__ import annotations

import argparse
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import zipfile


ANDROID_PLATFORM = "android_aarch64"
ANDROID_ABI = "arm64-v8a"
ELF_AARCH64 = 183


class PackageError(ValueError):
    """A supplied archive is not the expected Android package."""


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _elf_aarch64(archive: zipfile.ZipFile, member: str) -> None:
    with archive.open(member) as source:
        header = source.read(64)
    if len(header) < 64 or header[:4] != b"\x7fELF":
        raise PackageError(f"{member}: missing or truncated ELF header")
    # ELF64, little-endian, current ELF version. Android ARM64 uses all three.
    if header[4:7] != b"\x02\x01\x01":
        raise PackageError(f"{member}: expected a 64-bit little-endian ELF library")
    machine = struct.unpack_from("<H", header, 18)[0]
    if machine != ELF_AARCH64:
        raise PackageError(f"{member}: expected AArch64 ELF machine 183, got {machine}")


def _module_members(names: list[str], package: str, module: str) -> list[str]:
    pattern = re.compile(rf"{re.escape(module)}(?:\.[^.]+)*\.so(?:\.\d+)*$")
    return [name for name in names
            if name.startswith(package + "/") and pattern.fullmatch(PurePosixPath(name).name)]


def check_wheel(path: Path, package: str, version: str) -> int:
    """Validate METADATA/WHEEL and the native binding modules in one wheel."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata_paths = [name for name in names
                          if len(PurePosixPath(name).parts) == 2
                          and name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise PackageError(f"{path.name}: expected exactly one top-level METADATA")
        metadata_path = metadata_paths[0]
        metadata = BytesParser().parsebytes(archive.read(metadata_path))
        if _normalise_name(metadata.get("Name", "")) != _normalise_name(package):
            raise PackageError(f"{path.name}: expected package {package}, got {metadata.get('Name')!r}")
        if metadata.get("Version") != version:
            raise PackageError(f"{path.name}: expected version {version}, got {metadata.get('Version')!r}")
        wheel_path = str(PurePosixPath(metadata_path).with_name("WHEEL"))
        if wheel_path not in names:
            raise PackageError(f"{path.name}: missing WHEEL metadata")
        wheel = BytesParser().parsebytes(archive.read(wheel_path))
        tags = wheel.get_all("Tag", [])
        if not tags or any(tag.rsplit("-", 1)[-1] != ANDROID_PLATFORM for tag in tags):
            raise PackageError(f"{path.name}: expected only {ANDROID_PLATFORM} wheel tags, got {tags!r}")

        package_dir = "PySide6" if _normalise_name(package) == "pyside6" else "shiboken6"
        modules = ("QtCore", "QtGui", "QtWidgets") if package_dir == "PySide6" else ("Shiboken",)
        checked = 0
        for module in modules:
            matches = _module_members(names, package_dir, module)
            if not matches:
                raise PackageError(f"{path.name}: missing {package_dir}/{module} native module")
            for member in matches:
                _elf_aarch64(archive, member)
                checked += 1
        if package_dir == "shiboken6":
            runtimes = _module_members(names, package_dir, "libshiboken6")
            if not runtimes:
                raise PackageError(f"{path.name}: missing shiboken6/libshiboken6 native runtime")
            for member in runtimes:
                _elf_aarch64(archive, member)
                checked += 1
        return checked


def check_apk(path: Path) -> int:
    """Validate packaged Qt libraries and every library under the ARM64 ABI."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        windows = [name for name in names if name.lower().endswith((".dll", ".pyd"))]
        if windows:
            raise PackageError(f"{path.name}: Windows binary found: {windows[0]}")
        prefix = f"lib/{ANDROID_ABI}/"
        members = [name for name in names if name.startswith(prefix) and name.endswith(".so")]
        if not members:
            raise PackageError(f"{path.name}: no native libraries in {prefix}")
        for module in ("Core", "Gui", "Widgets"):
            pattern = re.compile(rf"libQt6{module}(?:_{re.escape(ANDROID_ABI)})?\.so$")
            if not any(pattern.fullmatch(PurePosixPath(name).name) for name in members):
                raise PackageError(f"{path.name}: missing Qt6{module} runtime in {prefix}")
        for member in members:
            _elf_aarch64(archive, member)
        return len(members)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyside-wheel", type=Path)
    parser.add_argument("--shiboken-wheel", type=Path)
    parser.add_argument("--version", default="6.12.0", help="Expected matching Qt for Python version")
    parser.add_argument("--apk", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    if bool(args.pyside_wheel) != bool(args.shiboken_wheel):
        parser.error("--pyside-wheel and --shiboken-wheel must be supplied together")
    if not args.pyside_wheel and not args.apk:
        parser.error("supply a pair of Android wheels or at least one --apk")
    try:
        if args.pyside_wheel:
            for path, package in ((args.pyside_wheel, "PySide6"),
                                  (args.shiboken_wheel, "shiboken6")):
                count = check_wheel(path, package, args.version)
                print(f"OK {path.name}: {package} {args.version}, {ANDROID_PLATFORM}, {count} native modules")
        for path in args.apk:
            count = check_apk(path)
            print(f"OK {path.name}: Qt Core/Gui/Widgets, {count} ARM64 native libraries, no Windows DLLs")
    except (PackageError, OSError, zipfile.BadZipFile, KeyError) as error:
        print(f"Android package check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
