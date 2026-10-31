"""Offline archive fixtures for Android package validation; no Android SDK needed."""
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
import zipfile

from check_android_package import PackageError, check_apk, check_wheel


def elf(machine=183, elf_class=2):
    header = bytearray(64)
    header[:7] = b"\x7fELF" + bytes((elf_class, 1, 1))
    struct.pack_into("<HHI", header, 16, 3, machine, 1)
    return bytes(header)


def wheel_members(package="PySide6", version="6.12.0", platform="android_aarch64"):
    dist = f"{package.lower()}-{version}.dist-info"
    result = {
        f"{dist}/METADATA": f"Metadata-Version: 2.4\nName: {package}\nVersion: {version}\n",
        f"{dist}/WHEEL": f"Wheel-Version: 1.0\nRoot-Is-Purelib: false\nTag: cp310-abi3-{platform}\n",
    }
    if package == "PySide6":
        result.update({f"PySide6/{module}.abi3.so": elf()
                       for module in ("QtCore", "QtGui", "QtWidgets")})
    else:
        result.update({f"shiboken6/{module}.abi3.so": elf()
                       for module in ("Shiboken", "libshiboken6")})
    return result


def apk_members():
    return {f"lib/arm64-v8a/libQt6{module}_arm64-v8a.so": elf()
            for module in ("Core", "Gui", "Widgets")}


def python_bundle(members=None, prefix=""):
    stdlib = io.BytesIO()
    with zipfile.ZipFile(stdlib, "w") as archive:
        archive.writestr("json/__init__.pyc", b"offline fixture")
    contents = {"stdlib.zip": stdlib.getvalue(), "modules/_ssl.so": elf(),
                "site-packages/example.pyc": b"offline fixture"}
    if members is not None:
        contents = members
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, content in contents.items():
            entry = tarfile.TarInfo(prefix + name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    return output.getvalue()


class AndroidPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pawchive_android_check_")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def archive(self, name, members):
        path = self.root / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member, content in members.items():
                archive.writestr(member, content)
        return path

    def test_matching_wheels_and_arm64_apk_pass(self):
        pyside = self.archive("pyside.whl", wheel_members())
        shiboken = self.archive("shiboken.whl", wheel_members("shiboken6"))
        apk = self.archive("app.apk", apk_members())
        self.assertEqual(check_wheel(pyside, "PySide6", "6.12.0"), 3)
        self.assertEqual(check_wheel(shiboken, "shiboken6", "6.12.0"), 2)
        self.assertEqual(check_apk(apk), 3)

    def test_wrong_wheel_version_platform_or_package_is_rejected(self):
        for package, version, platform, expected_error in (
            ("PySide6", "6.11.3", "android_aarch64", "expected version"),
            ("PySide6", "6.12.0", "win_amd64", "wheel tags"),
            ("PySide6", "6.12.0", "android_x86_64", "wheel tags"),
            ("shiboken6", "6.12.0", "android_aarch64", "expected package"),
        ):
            with self.subTest(package=package, version=version, platform=platform):
                path = self.archive("wrong.whl", wheel_members(package, version, platform))
                with self.assertRaisesRegex(PackageError, expected_error):
                    check_wheel(path, "PySide6", "6.12.0")

    def test_metadata_alone_is_insufficient_and_wrong_native_architecture_fails(self):
        for bad_member in (None, elf(machine=62), elf(elf_class=1), b"MZ" + bytes(62)):
            with self.subTest(header=bad_member):
                members = wheel_members()
                if bad_member is None:
                    del members["PySide6/QtCore.abi3.so"]
                else:
                    members["PySide6/QtCore.abi3.so"] = bad_member
                with self.assertRaises(PackageError):
                    check_wheel(self.archive("bad-native.whl", members), "PySide6", "6.12.0")
        members = wheel_members("shiboken6")
        members["shiboken6/libshiboken6.abi3.so"] = elf(machine=62)
        with self.assertRaisesRegex(PackageError, "AArch64"):
            check_wheel(self.archive("bad-shiboken.whl", members), "shiboken6", "6.12.0")

    def test_apk_requires_each_qt_runtime_and_rejects_windows_binaries(self):
        for bad_member, content, expected_error in (
            ("lib/arm64-v8a/libQt6Gui_arm64-v8a.so", None, "missing Qt6Gui"),
            ("assets/Qt6Core.dll", b"MZ", "Windows binary"),
            ("lib/arm64-v8a/QtCore.pyd", b"MZ", "Windows binary"),
            ("lib/arm64-v8a/libother.so", elf(machine=62), "AArch64"),
        ):
            with self.subTest(member=bad_member):
                members = apk_members()
                if content is None:
                    del members[bad_member]
                else:
                    members[bad_member] = content
                with self.assertRaisesRegex(PackageError, expected_error):
                    check_apk(self.archive("bad.apk", members))

    def test_p4a_python_resource_bundle_is_not_mistaken_for_an_elf_library(self):
        for prefix in ("", "_python_bundle/", "_python_bundle__arm64-v8a/"):
            with self.subTest(prefix=prefix):
                members = apk_members()
                members["lib/arm64-v8a/libpybundle.so"] = python_bundle(prefix=prefix)
                self.assertEqual(check_apk(self.archive("p4a.apk", members)), 4)

    def test_only_the_exact_p4a_bundle_path_gets_resource_archive_validation(self):
        members = apk_members()
        members["lib/arm64-v8a/libother.so"] = python_bundle()
        with self.assertRaisesRegex(PackageError, "ELF"):
            check_apk(self.archive("wrong-name.apk", members))

    def test_bad_python_bundle_contents_are_not_exempt_from_checks(self):
        for payload, message in (
            (b"not a tar archive", "invalid python-for-android"),
            (python_bundle({"anything.txt": b"not a Python bundle"}), "missing standard library"),
            (python_bundle({"stdlib.zip": b"not a zip", "modules/_ssl.so": elf()}), "ZIP header"),
            (python_bundle({"modules/_ssl.so": elf(machine=62)}), "AArch64"),
            (python_bundle({"site-packages/QtCore.pyd": b"MZ"}), "Windows binary"),
        ):
            with self.subTest(message=message):
                members = apk_members()
                members["lib/arm64-v8a/libpybundle.so"] = payload
                with self.assertRaisesRegex(PackageError, message):
                    check_apk(self.archive("bad-bundle.apk", members))


if __name__ == "__main__":
    unittest.main()
