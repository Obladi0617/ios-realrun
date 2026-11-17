"""Keep bundled DLLs out of independently installed programs such as the SDK."""

import ctypes
import ntpath
import os
import subprocess
import sys
import threading
from contextlib import contextmanager


_dll_lock = threading.RLock()


def _get_dll_directory():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_directory = kernel.GetDllDirectoryW
    get_directory.argtypes = (ctypes.c_uint32, ctypes.c_wchar_p)
    get_directory.restype = ctypes.c_uint32
    size = get_directory(0, None)
    if not size:
        return None
    buffer = ctypes.create_unicode_buffer(size + 1)
    if not get_directory(len(buffer), buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def _set_dll_directory(directory):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    set_directory = kernel.SetDllDirectoryW
    set_directory.argtypes = (ctypes.c_wchar_p,)
    set_directory.restype = ctypes.c_int
    if not set_directory(directory):
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def system_library_search():
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    with _dll_lock:
        original = _get_dll_directory()
        _set_dll_directory(None)
        try:
            yield
        finally:
            _set_dll_directory(original)


def clean_environment(environment=None):
    result = dict(os.environ if environment is None else environment)
    bundle = getattr(sys, "_MEIPASS", None)
    if sys.platform == "win32" and getattr(sys, "frozen", False) and bundle:
        bundle = ntpath.normcase(ntpath.normpath(str(bundle)))
        result["PATH"] = ";".join(
            part for part in result.get("PATH", "").split(";")
            if ntpath.normcase(ntpath.normpath(part)) != bundle
            and not ntpath.normcase(ntpath.normpath(part)).startswith(bundle + "\\")
        )
    return result


def external_popen(command, **kwargs):
    kwargs["env"] = clean_environment(kwargs.get("env"))
    with system_library_search():
        return subprocess.Popen(command, **kwargs)


def external_run(command, **kwargs):
    kwargs["env"] = clean_environment(kwargs.get("env"))
    with system_library_search():
        return subprocess.run(command, **kwargs)
