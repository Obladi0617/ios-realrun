"""Keep user preferences outside the installation directory."""

import json
import math
import os
import tempfile
from pathlib import Path


DEFAULTS = {
    "backend": "ios",
    "route": "ZJGroute.txt",
    "speed": "3.3333",  # 5:00 per kilometre.
    "minutes": "30",
    "profile": "recreational",
    "serial": "",
    "avd": "",
    "sdk": "",
    "app": "tyys",
    "android_home": "",
    "android_gpu": "auto",
    "scrcpy": "",
    "login_tyys": "",
    "login_ding": "",
}
ROUTES = ("ZJGroute.txt", "YQroute.txt", "HNroute.txt")


def data_dir() -> Path:
    override = os.environ.get("IOSREALRUN_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".local" / "share") / "iOSRealRun"


def validate_run(speed, minutes):
    speed, minutes = float(speed), int(minutes)
    if not math.isfinite(speed) or not 0.1 <= speed <= 100 or minutes < 0:
        raise ValueError("速度范围为 0.1–100 m/s，时长必须是非负整数。")
    return speed, minutes


def load_settings(path=None):
    result = dict(DEFAULTS)
    try:
        saved = json.loads((Path(path) if path else data_dir() / "settings.json").read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return result
        result.update({key: value for key, value in saved.items() if key in DEFAULTS and isinstance(value, str)})
        validate_run(result["speed"], result["minutes"])
    except (OSError, ValueError, TypeError, OverflowError):
        return dict(DEFAULTS)
    if result["backend"] not in ("ios", "android"):
        result["backend"] = DEFAULTS["backend"]
    if result["route"] not in ROUTES:
        result["route"] = DEFAULTS["route"]
    if result["profile"] not in ("constant", "steady", "recreational", "variable"):
        result["profile"] = DEFAULTS["profile"]
    if result["android_gpu"] not in ("auto", "host", "swiftshader"):
        result["android_gpu"] = DEFAULTS["android_gpu"]
    return result


def save_settings(settings, path=None):
    target = Path(path) if path else data_dir() / "settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    saved = {key: str(settings.get(key, default)) for key, default in DEFAULTS.items()}
    fd, temporary = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(saved, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
