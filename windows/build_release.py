"""Build and check the portable Windows EXE in a dedicated virtual environment."""
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from build_support import is_icu_dll, verify_system_icu


def main():
    if sys.platform != 'win32' or struct.calcsize('P') != 8:
        raise SystemExit('Use 64-bit Windows and 64-bit Python to build this release.')
    if sys.prefix == sys.base_prefix:
        raise SystemExit('Create a dedicated .venv and install requirements-build.txt first.')
    for name, expected in [('PySide6-Essentials', '6.12.0'), ('shiboken6', '6.12.0'),
                           ('PyInstaller', '6.22.3'), ('pyinstaller-hooks-contrib', '2026.8')]:
        if metadata.version(name) != expected:
            raise SystemExit(f'Unexpected {name} version; install requirements-build.txt.')
    directory = Path(__file__).resolve().parent
    qt_core = metadata.distribution('PySide6-Essentials').locate_file('PySide6/Qt6Core.dll')
    count = verify_system_icu(qt_core)
    print(f'System ICU satisfies all {count} Qt import symbols.', flush=True)
    env = os.environ.copy()
    windir = Path(env.get('WINDIR', 'C:/Windows'))
    # Prevent native libraries from unrelated software from entering analysis.
    env['PATH'] = os.pathsep.join([str(Path(sys.executable).parent),
                                str(windir / 'System32'), str(windir)])
    env['PYTHONNOUSERSITE'] = '1'
    for name in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                 'QML2_IMPORT_PATH', 'QML_IMPORT_PATH', 'QT_QPA_PLATFORM'):
        env.pop(name, None)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(directory / 'PawchiveDownloader.spec')],
                   cwd=directory, env=env, check=True)
    binary = directory / 'dist' / 'PawchiveDownloader.exe'
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(binary))
    bundled_icu = [name for name in archive.toc if is_icu_dll(name)]
    if bundled_icu:
        raise RuntimeError('A system ICU replacement entered the bundle: ' + ', '.join(bundled_icu))
    env['PATH'] = os.pathsep.join([str(windir / 'System32'), str(windir)])
    env['QT_QPA_PLATFORM'] = 'offscreen'
    with tempfile.TemporaryDirectory(prefix='pawchive_exe_check_') as temporary:
        report_path = Path(temporary) / 'startup.json'
        process = subprocess.Popen([str(binary), '--self-test-output', str(report_path)],
                                   cwd=temporary, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            process.communicate(timeout=10)
            raise RuntimeError('The frozen startup check timed out; do not publish this build.')
        if process.returncode or not report_path.is_file():
            raise RuntimeError('The frozen startup check failed: ' + stderr.decode('utf-8', 'replace')[-2000:])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        if not report['ok'] or stderr.strip():
            raise RuntimeError(f'The frozen GUI check reported an error: {report!r} {stderr!r}')
        (directory / 'dist' / 'startup-check.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Build verified: ' + str(binary), flush=True)


if __name__ == '__main__':
    main()
