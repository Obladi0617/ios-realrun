"""Compare local rendering with repeatable Settings scrolling, without a window.

Does not enter an account, submit app actions, change GPS, or clear app data.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def measure(adb, serial, scrcpy, output, optimized=False):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    def shell(*arguments):
        return subprocess.check_output([adb, "-s", serial, "shell", *arguments],
                                       text=True, encoding="utf-8", errors="replace", timeout=45)

    size = shell("wm", "size")
    width, height = map(int, re.findall(r"(\d+)x(\d+)", size)[-1])
    result = {"serial": serial, "size": size.strip(), "density": shell("wm", "density").strip(),
              "memory": shell("head", "-n", "3", "/proc/meminfo").strip(),
              "renderer": next((line.strip() for line in shell("dumpsys", "SurfaceFlinger").splitlines()
                                if line.startswith("GLES:")), "unknown"),
              "workload": "Android Settings: eight alternating 600 ms vertical scrolls"}
    shell("am", "start", "-W", "-a", "android.settings.SETTINGS")
    time.sleep(2)
    shell("dumpsys", "gfxinfo", "com.android.settings", "reset")
    arguments = [scrcpy, "--serial", serial, "--no-audio", "--no-playback", "--no-window",
                 "--no-control", "--time-limit=14", "--max-size=1280",
                 "--record=" + str(output.with_suffix(".mp4"))]
    if optimized:
        arguments.extend(("--max-fps=30", "--video-bit-rate=4M"))
    result["mirror_arguments"] = arguments[1:]
    log_path = output.with_suffix(".scrcpy.log")
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(arguments, env=dict(os.environ, ADB=adb),
                                   stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        try:
            time.sleep(2)
            x, bottom, top = int(width * .75), int(height * .8), int(height * .3)
            commands = []
            for i in range(8):
                start, end = (bottom, top) if i % 2 == 0 else (top, bottom)
                commands.append(f"input swipe {x} {start} {x} {end} 600")
            begin = time.monotonic()
            shell("; ".join(commands))
            result["scroll_seconds"] = round(time.monotonic() - begin, 3)
            result["record_exit"] = process.wait(timeout=30)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
    graphics = shell("dumpsys", "gfxinfo", "com.android.settings")
    result["focus"] = next((line.strip() for line in shell("dumpsys", "window").splitlines()
                            if "mCurrentFocus=" in line), "unknown")
    output.with_suffix(".gfxinfo.txt").write_text(graphics, encoding="utf-8")
    for key, pattern in {
        "frames": r"Total frames rendered: (\d+)",
        "jank_percent": r"Janky frames: \d+ \(([\d.]+)%\)",
        "p50_ms": r"50th percentile: (\d+)ms",
        "p90_ms": r"90th percentile: (\d+)ms",
        "p95_ms": r"95th percentile: (\d+)ms",
        "p99_ms": r"99th percentile: (\d+)ms",
    }.items():
        match = re.search(pattern, graphics)
        result[key] = float(match[1]) if match else None
    result["valid_scroll"] = result["frames"] is not None and result["frames"] >= 100 and "Not Responding" not in result["focus"]
    result["record_bytes"] = output.with_suffix(".mp4").stat().st_size
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["valid_scroll"] or result["record_exit"]:
        raise SystemExit("Invalid scrolling measurement; inspect focus and capture log.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--scrcpy", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--optimized", action="store_true")
    args = parser.parse_args()
    measure(**vars(args))
