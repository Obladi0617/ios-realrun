"""Compare desktop telemetry with independent Android GPS callbacks, via CLI."""

import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
import urllib.request


def distance(a, b):
    lat1, lat2 = math.radians(a["latitude"]), math.radians(b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(b["longitude"] - a["longitude"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", type=Path, required=True)
    parser.add_argument("--sdk", required=True)
    parser.add_argument("--avd", required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--speed", type=float, default=4.8)
    parser.add_argument("--profile", choices=("constant", "steady", "recreational", "variable"), default="steady")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    connection = json.loads(args.connection.read_text(encoding="utf-8"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path, body=None):
        headers = {"Authorization": "Bearer " + connection["token"]}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(connection["origin"] + path,
                                         data=None if body is None else json.dumps(body).encode(), headers=headers)
        with opener.open(request, timeout=10) as response:
            return json.load(response)

    def command(*parameters):
        return subprocess.check_output([str(Path(args.sdk) / "platform-tools" / "adb.exe"),
                                        "-s", args.serial, *parameters],
                                       text=True, encoding="utf-8", errors="replace", timeout=30)

    if command("emu", "avd", "name").splitlines()[0].strip() != args.avd:
        raise RuntimeError("Refusing to change an unexpected AVD")
    if api("/api/state")["busy"]:
        raise RuntimeError("Refusing to interrupt an active job")
    package = "local.realrun.gpsprobe"
    for permission in ("ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION"):
        command("shell", "pm", "grant", package, "android.permission." + permission)
    command("shell", "am", "start", "-S", "-W", "-n", package + "/.GpsProbe")
    pid = command("shell", "pidof", package).split()[0]
    api("/api/settings", {"backend": "android", "speed": str(args.speed), "minutes": "1", "profile": args.profile})
    points, run_id, cursor = [], "", 0
    try:
        api("/api/action", {"action": "run"})
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            state = api(f"/api/state?cursor={cursor}&run={run_id}")
            if state["run"]["id"] != run_id:
                points = []
            run_id = state["run"]["id"]
            points.extend(state["run"]["points"])
            cursor = state["run"]["cursor"]
            if state["task"]["status"] == "error":
                raise RuntimeError(state["task"]["label"])
            time.sleep(.15)
    finally:
        api("/api/action", {"action": "stop"})
        for _ in range(100):
            state = api(f"/api/state?cursor={cursor}&run={run_id}")
            points.extend(state["run"]["points"])
            cursor = state["run"]["cursor"]
            if not state["busy"]:
                break
            time.sleep(.1)
        time.sleep(1.2)
        raw = command("logcat", "-d", "--pid=" + pid, "-v", "raw", "-s", "RealRunGPSProbe:I", "*:S")
        command("shell", "am", "force-stop", package)
    fixes = [json.loads(line) for line in raw.splitlines() if line.startswith("{")]
    window = [point for point in points if point["elapsed"] >= 3]
    if len(window) < 10:
        raise RuntimeError("Not enough confirmed coordinates for comparison")
    matches = []
    for fix in fixes:
        nearest = min(window, key=lambda point: distance(point, fix))
        if distance(nearest, fix) < .3 and fix["speed"] > .05:
            matches.append({"sequence": nearest["sequence"], "ui_speed": nearest["speed"],
                            "gps_speed": fix["speed"], "elapsedNanos": fix.get("elapsedNanos"),
                            "latitude": fix["latitude"], "longitude": fix["longitude"]})
    if len(matches) < 5:
        raise RuntimeError("Independent GPS samples did not match accepted coordinates")
    measured = (window[-1]["distance"] - window[0]["distance"]) / (window[-1]["elapsed"] - window[0]["elapsed"])
    first_samples = {}
    for sample in matches:
        first_samples.setdefault(sample["sequence"], sample)
    unique = list(first_samples.values())
    unique.sort(key=lambda sample: sample["sequence"])
    gps_duration = (unique[-1]["elapsedNanos"] - unique[0]["elapsedNanos"]) / 1e9
    gps_distance = sum(distance(a, b) for a, b in zip(unique, unique[1:]))
    summary = {"version": state["version"], "profile": args.profile, "target_mps": args.speed, "configured_pace_seconds_per_km": 1000 / args.speed,
               "host_coordinate_mean_mps": measured, "android_coordinate_mean_mps": gps_distance / gps_duration,
               "ui_speed_median_mps": statistics.median(p["speed"] for p in window),
               "android_reported_speed_median_mps": statistics.median(p["gps_speed"] for p in matches),
               "ui_android_speed_mae_mps": statistics.mean(abs(p["gps_speed"] - p["ui_speed"]) for p in matches),
               "ui_speed_range_mps": [min(p["speed"] for p in window), max(p["speed"] for p in window)],
               "confirmed_points": len(points), "gps_callbacks": len(fixes), "matched_callbacks": len(matches),
               "android_speed_after_stop_mps": fixes[-1]["speed"],
               "stopped": not state["busy"] and state["run"]["status"] == "stopped"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"summary": summary, "points": points, "gps": fixes, "matches": matches},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
