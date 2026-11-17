"""Opt-in GPS integration check against an explicitly named disposable AVD."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from android_emulator import AndroidEmulator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--avd-name", required=True)
    parser.add_argument("--apk", type=Path, required=True, help="GPS probe built from tests/android_probe")
    parser.add_argument("--worker", type=Path, help="Test the packaged worker instead of Python source")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    device = AndroidEmulator(args.sdk, args.serial)
    device.check()
    name = device.command("emu", "avd", "name").splitlines()[0]
    if name != args.avd_name:
        raise RuntimeError("The connected AVD does not match --avd-name; refusing to modify it.")

    print(device.install_apk(args.apk), flush=True)
    package = "local.realrun.gpsprobe"
    for permission in ("ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION"):
        device.command("shell", "pm", "grant", package, "android.permission." + permission)
    mode = device.command("shell", "settings", "get", "secure", "location_mode", timeout=60)
    if mode == "0":
        device.command("shell", "cmd", "location", "set-location-enabled", "true", timeout=60)
    device.command("logcat", "-c")
    print(device.command("shell", "am", "start", "-W", "-n", package + "/.GpsProbe", timeout=60), flush=True)

    command = [str(args.worker.resolve())] if args.worker else [sys.executable, str(ROOT / "worker.py")]
    command.extend(("--backend", "android", "--sdk", args.sdk, "--serial", args.serial,
                    "--run", "--route", "ZJGroute.txt", "--speed", "4.8", "--minutes", "1"))
    try:
        with tempfile.TemporaryDirectory(prefix="realrun-live-") as directory:
            stop = Path(directory) / "stop.flag"
            environment = dict(os.environ, IOSREALRUN_STOP_FILE=str(stop), PYTHONIOENCODING="utf-8")
            log_path = Path(directory) / "route.log"
            with log_path.open("w", encoding="utf-8") as log:
                process = subprocess.Popen(command, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    time.sleep(10)
                    stop.write_text("stop", encoding="utf-8")
                    code = process.wait(timeout=15)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
            route_log = log_path.read_text(encoding="utf-8")
        raw = device.command("logcat", "-d", "-v", "raw", "-s", "RealRunGPSProbe:I", "*:S")
    finally:
        device.command("shell", "am", "force-stop", package)

    positions = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
    result = {
        "serial": device.serial,
        "avd": name,
        "packaged_worker": args.worker is not None,
        "apk_install": True,
        "route_exit": code,
        "gps_updates": len(positions),
        "coordinates_changed": len({(p["latitude"], p["longitude"]) for p in positions}) > 1,
        "reported_speed_positive": any(p["speed"] > 0 for p in positions),
        "stopped_gracefully": code == 0 and "推送已停止" in route_log,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    if not all(result[key] for key in ("coordinates_changed", "reported_speed_positive", "stopped_gracefully")):
        print(route_log, flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
