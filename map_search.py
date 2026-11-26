"""User-initiated worldwide place search with coordinate input."""

from functools import lru_cache
import json
import os
import re
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from app_info import APP_VERSION, GITHUB_REPOSITORY
from fixed_location import validate_point


PHOTON_URL = "https://photon.komoot.io/api/"
MAX_RESULT_BYTES = 128 * 1024
_request_lock = threading.Lock()
_last_request = 0.0
_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_COORDINATES = re.compile(rf"({_NUMBER})(?:\s*[,，]\s*|\s+)({_NUMBER})")


def search_places(query):
    query = " ".join(query.split())
    if not query or len(query) > 160:
        raise ValueError("请输入 1 到 160 个字符的地点名称或坐标。")
    if match := _COORDINATES.fullmatch(query):
        point = validate_point(*match.groups())
        return [{"label": f"{point['latitude']:.6f}, {point['longitude']:.6f}", **point}]

    endpoint = os.environ.get("REALRUN_PHOTON_URL") or PHOTON_URL
    parsed = urlsplit(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("地点搜索服务地址无效。")
    return _search_photon(endpoint, query)


@lru_cache(maxsize=96)
def _search_photon(endpoint, query):
    global _last_request
    url = endpoint + "?" + urlencode({"q": query, "limit": 6})
    request = Request(url, headers={
        "User-Agent": f"RealRun/{APP_VERSION} (+https://github.com/{GITHUB_REPOSITORY})",
        "Accept": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        with _request_lock:
            time.sleep(max(0, 1.1 - (time.monotonic() - _last_request)))
            _last_request = time.monotonic()
            with urlopen(request, timeout=7) as response:
                raw = response.read(MAX_RESULT_BYTES + 1)
        if len(raw) > MAX_RESULT_BYTES:
            raise ValueError("search response too large")
        features = json.loads(raw)["features"]
        if not isinstance(features, list):
            raise ValueError("invalid search results")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RuntimeError("地点搜索暂时不可用。可重试，或直接输入纬度和经度。") from error

    results = []
    for feature in features[:6]:
        try:
            longitude, latitude = feature["geometry"]["coordinates"][:2]
            point = validate_point(latitude, longitude)
            properties = feature["properties"]
            parts = [properties.get(key) for key in ("name", "street", "district", "city", "state", "country")]
            label = " · ".join(dict.fromkeys(part for part in parts if isinstance(part, str) and part))
            if label:
                results.append({"label": label[:240], **point})
        except (KeyError, TypeError, ValueError):
            continue
    return results
