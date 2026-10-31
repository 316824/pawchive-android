"""Load the OS ICU before Qt, independently of PATH and adjacent applications."""
import sys

if sys.platform == 'win32' and getattr(sys, 'frozen', False):
    import ctypes

    # LOAD_LIBRARY_SEARCH_SYSTEM32: never load an incompatible same-name DLL
    # from a third-party program. Do not redistribute Windows' forwarding DLLs.
    _windows_icu = ctypes.WinDLL('icuuc.dll', winmode=0x00000800)
