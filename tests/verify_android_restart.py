"""Opt-in, command-line restart check against an explicitly selected AVD."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--avd", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    connection = json.loads(args.connection.read_text(encoding="utf-8"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path, body=None):
        headers = {"Authorization": "Bearer " + connection["token"]}
        data = None if body is None else json.dumps(body).encode("utf-8")
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(connection["origin"] + path, data=data, headers=headers)
        with opener.open(request, timeout=15) as response:
            return json.load(response)

    def command(*parameters):
        return subprocess.check_output([str(Path(args.sdk) / "platform-tools" / "adb.exe"),
                                        "-s", args.serial, *parameters],
                                       text=True, encoding="utf-8", errors="replace", timeout=45)

    if command("emu", "avd", "name").splitlines()[0].strip() != args.avd:
        raise RuntimeError("Refusing to restart an unexpected AVD")
    if api("/api/state")["busy"]:
        raise RuntimeError("Refusing to interrupt an active desktop job")

    def package_identity(package):
        text = command("shell", "dumpsys", "package", package)
        return {key: re.search(pattern, text)[1] for key, pattern in {
            "version": r"\bversionName=(\S+)", "uid": r"\b(?:userId|appId)=(\d+)",
            "first_install": r"\bfirstInstallTime=([^\r\n]+)",
        }.items()}

    packages = ("net.crigh.mysport", "com.alibaba.android.rimet")
    before = {package: package_identity(package) for package in packages}
    api("/api/settings", {"backend": "android", "sdk": args.sdk, "avd": args.avd,
                           "android_home": args.home, "serial": args.serial, "android_gpu": "auto"})
    api("/api/action", {"action": "restart_phone"})
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        state = api("/api/state")
        if not state["busy"]:
            if state["task"]["status"] != "success":
                raise RuntimeError(state["task"]["label"])
            break
        time.sleep(.5)
    else:
        raise RuntimeError("Restart did not finish within 180 seconds")

    after = {package: package_identity(package) for package in packages}
    surface = command("shell", "dumpsys", "SurfaceFlinger")
    renderer = next(line.strip() for line in surface.splitlines() if line.startswith("GLES:"))
    result = {"version": state["version"], "avd": args.avd, "serial": state["device"]["serial"],
              "restart_success": True, "packages_unchanged": before == after, "packages": after,
              "renderer": renderer, "size": command("shell", "wm", "size").strip(),
              "density": command("shell", "wm", "density").strip(),
              "memory": command("shell", "head", "-n", "3", "/proc/meminfo").strip(),
              "phone_window_not_started": state["phone"]["status"] == "closed"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["packages_unchanged"] or not result["phone_window_not_started"]:
        raise SystemExit("Restart changed packages or opened an unexpected window")


if __name__ == "__main__":
    main()
