"""Portable defaults for the official emulator and its screen stream."""

import ctypes
import os
import re


GRAPHICS_MODES = ("auto", "host", "swiftshader")
MIRROR_VIDEO_OPTIONS = ("--max-size=1280", "--max-fps=30", "--video-bit-rate=4M", "--no-mouse-hover")


def host_memory_mb():
    """Return physical/available memory; failure leaves conservative defaults."""
    try:
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32),
                            *[(name, ctypes.c_uint64) for name in
                              ("total", "available", "page_total", "page_available",
                               "virtual_total", "virtual_available", "extended")]]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return 0, 0
            return status.total // 1048576, status.available // 1048576
        page_size = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page_size // 1048576
        try:
            available = os.sysconf("SC_AVPHYS_PAGES") * page_size // 1048576
        except (ValueError, OSError):
            available = total // 2
        return total, available
    except (AttributeError, OSError, ValueError):
        return 0, 0


def launch_resources():
    total, available = host_memory_mb()
    memory = 4096 if total >= 16384 and available >= 6144 else (
        3072 if total >= 12288 and available >= 4096 else 2560)
    cores = max(1, min(4, (os.cpu_count() or 2) // 2))
    return memory, cores


def graphics_failure(log):
    """Only retry driver/renderer failures, never disk, AVD or permission errors."""
    return bool(re.search(
        r"(?:failed to|could not|cannot|unable to) (?:initialize|load|create|find)[^\n]*"
        r"(?:graphics|renderer|vulkan|opengl|egl|framebuffer|libGL)|"
        r"(?:gpu|vulkan|opengles?|egl|renderer)[^\n]*(?:initialization failed|failed to initialize|fatal|crashed)|"
        r"VK_ERROR_(?:INITIALIZATION_FAILED|INCOMPATIBLE_DRIVER|DEVICE_LOST)",
        log, re.IGNORECASE))


def optimize_display(device, message=lambda _: None):
    """Reduce default high-DPI phone rendering; respect existing user overrides."""
    size = device.command("shell", "wm", "size")
    density = device.command("shell", "wm", "density")
    if "Override" in size or "Override" in density:
        return
    dimensions = re.search(r"Physical size:\s*(\d+)x(\d+)", size)
    dpi = re.search(r"Physical density:\s*(\d+)", density)
    if not dimensions or not dpi:
        return
    width, height = map(int, dimensions.groups())
    if min(width, height) <= 0:
        return
    scale = min(1.0, 720 / min(width, height), 1600 / max(width, height))
    if scale >= .95:
        return
    target = f"{int(width * scale) // 2 * 2}x{int(height * scale) // 2 * 2}"
    target_dpi = str(max(72, round(int(dpi[1]) * scale)))
    try:
        device.command("shell", "wm", "size", target)
        device.command("shell", "wm", "density", target_dpi)
    except RuntimeError:
        # Both were previously native, so rollback cannot overwrite user overrides.
        device.command("shell", "wm", "size", "reset")
        device.command("shell", "wm", "density", "reset")
        raise
    message(f"已调整虚拟手机渲染分辨率：{target}，保留原有界面比例。")
