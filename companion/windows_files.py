"""Reject Windows reparse points and check an opened artifact's final path."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat


def linked_path(path):
    """Python 3.11 is_symlink() alone does not identify Windows junctions."""
    path = Path(path)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def linked_windows_ancestor(path):
    if os.name != "nt":
        return False
    absolute = Path(os.path.abspath(path))
    return any(linked_path(part) for part in (absolute, *absolute.parents))


@contextmanager
def artifact_stream(path):
    """Open a regular artifact without silently following redirected Windows paths."""
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    else:
        import ctypes
        from ctypes import wintypes as w
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
        kernel.CreateFileW.restype = w.HANDLE
        kernel.GetFinalPathNameByHandleW.argtypes = [w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD]
        kernel.GetFinalPathNameByHandleW.restype = w.DWORD
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        expected = os.path.abspath(path)
        handle = kernel.CreateFileW(expected, 0x80000000, 1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "Cannot open generated artifact")
        try:
            final = ctypes.create_unicode_buffer(32768)
            count = kernel.GetFinalPathNameByHandleW(handle, final, len(final), 0)
            if not count or count >= len(final):
                raise OSError("Cannot verify generated artifact path")
            actual = final.value
            if actual.startswith("\\\\?\\UNC\\"):
                actual = "\\\\" + actual[8:]
            elif actual.startswith("\\\\?\\"):
                actual = actual[4:]
            if os.path.normcase(actual) != os.path.normcase(expected):
                raise OSError("Generated artifact path was redirected")
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            handle = None  # descriptor now owns the handle
        finally:
            if handle is not None:
                kernel.CloseHandle(handle)
    with os.fdopen(fd, "rb") as stream:
        yield stream
