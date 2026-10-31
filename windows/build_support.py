"""Keep Windows' own ICU implementation out of application bundles."""
import os
from pathlib import Path
import re


def is_icu_dll(name):
    # Also remove dependencies brought in by the accidentally collected ICU.
    # Qt in our pinned Windows wheel uses the OS' unversioned C entry points.
    basename = name.replace('\\', '/').rsplit('/', 1)[-1]
    return bool(re.fullmatch(r'icu(?:uc|in|dt)?\d*\.dll', basename, re.I))


def without_system_icu(binaries):
    return [entry for entry in binaries if not is_icu_dll(entry[0])]


def verify_system_icu(qt_core):
    """Compare PE imports with OS exports without loading third-party DLLs."""
    import pefile

    qt = pefile.PE(str(qt_core), fast_load=True)
    try:
        qt.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
        imports = {entry.dll.decode('ascii').lower(): entry.imports
                   for entry in qt.DIRECTORY_ENTRY_IMPORT
                   if is_icu_dll(entry.dll.decode('ascii'))}
        if not imports:
            raise RuntimeError('The pinned Qt Windows ICU import layout has changed; review the bundle rules.')
        checked = 0
        for name, symbols in imports.items():
            system = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32' / name
            dll = pefile.PE(str(system), fast_load=True)
            try:
                dll.parse_data_directories(directories=[
                    pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
                exports = {item.name for item in dll.DIRECTORY_ENTRY_EXPORT.symbols}
                missing = [item.name for item in symbols if item.name not in exports]
                if missing:
                    raise RuntimeError(f'System ICU cannot satisfy {len(missing)} Qt imports: {name}')
                checked += len(symbols)
            finally:
                dll.close()
        return checked
    finally:
        qt.close()
