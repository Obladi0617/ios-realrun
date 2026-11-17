"""CLI-only, opt-in iPhone smoke test through the actual desktop API and worker."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, help="Extracted Windows bundle to exercise")
    parser.add_argument("--storage", type=Path, required=True, help="Dedicated test state directory")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    args.storage.mkdir(parents=True, exist_ok=True)
    connection = args.storage / "connection.json"
    if connection.exists():
        raise RuntimeError("Use a fresh storage directory for each verification")
    command = ([str(args.bundle / "iOSRealRun.exe")] if args.bundle else [sys.executable, str(root / "desktop_app.py")])
    environment = dict(os.environ, IOSREALRUN_DATA_DIR=str(args.storage), PYTHONIOENCODING="utf-8")
    process = subprocess.Popen([*command, "--serve", "--connection-file", str(connection)],
                               env=environment, cwd=args.bundle or root,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    credentials = None
    report = {"packaged": bool(args.bundle), "success": False}

    def api(path="/api/state", payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(credentials["origin"] + path, data=data,
                                         headers={"Authorization": "Bearer " + credentials["token"],
                                                  "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)

    def idle(timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = api()
            if not state["busy"]:
                if state["task"]["status"] == "error":
                    raise RuntimeError(state["task"]["label"])
                return state
            time.sleep(.1)
        raise TimeoutError("Desktop task did not finish")

    def action(name):
        api("/api/action", {"action": name})

    try:
        deadline = time.monotonic() + 25
        while not connection.is_file():
            if process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Desktop executable failed to start its API")
            time.sleep(.1)
        credentials = json.loads(connection.read_text(encoding="utf-8"))
        state = api()
        report.update(version=state["version"], administrator=state["capabilities"]["admin"])
        if report["administrator"]:
            raise RuntimeError("Run this verification without administrator privileges")
        api("/api/settings", {"backend": "ios", "route": "ZJGroute.txt", "speed": "3.7",
                              "minutes": "1", "profile": "constant"})
        for name in ("check", "mount"):
            action(name)
            idle()
            report[name] = "passed"
        action("run")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = api()
            if state["run"]["pointCount"] >= 30:
                break
            if not state["busy"]:
                raise RuntimeError("iPhone worker stopped before accepting thirty fixes")
            time.sleep(.1)
        else:
            raise TimeoutError("No iPhone location fixes were accepted")
        action("stop")
        state = idle(timeout=30)
        if not any("已恢复真实定位" in item["text"] for item in state["logs"]):
            raise RuntimeError("Location clear did not complete successfully")
        if state["run"]["speed"] != 0 or state["run"]["status"] != "stopped":
            raise RuntimeError("Desktop did not finish stopping")
        report.update(success=True, acceptedFixes=state["run"]["pointCount"],
                      elapsedSeconds=state["run"]["elapsed"], distanceMetres=state["run"]["distance"],
                      locationCleared=True, stopped=True)
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if credentials is not None:
            try:
                action("stop")
                idle(timeout=30)
            except Exception:
                report["cleanupError"] = "Check the test desktop.log; device connection may have been lost"
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=10)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
