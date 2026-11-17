"""Refresh the small, attributed OpenStreetMap extracts shipped with the app."""

import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from run import bd09Towgs84
from util.route import parse_route


def main():
    output = ROOT / "frontend/public/maps"
    output.mkdir(parents=True, exist_ok=True)
    for route, name in (("ZJGroute.txt", "zjg"), ("YQroute.txt", "yuquan"), ("HNroute.txt", "haining")):
        points = [bd09Towgs84(p) for p in parse_route((ROOT / route).read_text(encoding="utf-8"))]
        west, east = min(p["lng"] for p in points) - .002, max(p["lng"] for p in points) + .002
        south, north = min(p["lat"] for p in points) - .002, max(p["lat"] for p in points) + .002
        url = f"https://api.openstreetmap.org/api/0.6/map?bbox={west:.6f},{south:.6f},{east:.6f},{north:.6f}"
        cached = ROOT / "build" / f"map-{name}.osm"
        if not cached.is_file():
            request = urllib.request.Request(url, headers={"User-Agent": "RealRun offline campus map build/1.4"})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("Map extract is unexpectedly large")
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        source = ET.parse(cached).getroot()
        nodes = {n.attrib["id"]: [round(float(n.attrib["lon"]), 6), round(float(n.attrib["lat"]), 6)] for n in source.findall("node")}
        features = []
        for way in source.findall("way"):
            tags = {tag.attrib["k"]: tag.attrib["v"] for tag in way.findall("tag")}
            kind = next((key for key in ("building", "highway", "natural", "waterway", "leisure") if key in tags), None)
            if kind is None or kind == "natural" and tags[kind] != "water":
                continue
            coordinates = [nodes[n.attrib["ref"]] for n in way.findall("nd") if n.attrib["ref"] in nodes]
            if len(coordinates) < 2:
                continue
            area = len(coordinates) >= 4 and coordinates[0] == coordinates[-1] and (kind in ("building", "natural") or kind == "leisure" and tags[kind] != "track")
            features.append({"type": "Feature", "properties": {"kind": kind, "value": tags[kind], "name": tags.get("name", "")},
                             "geometry": {"type": "Polygon" if area else "LineString", "coordinates": [coordinates] if area else coordinates}})
        collection = {"type": "FeatureCollection", "attribution": "© OpenStreetMap contributors", "license": "https://www.openstreetmap.org/copyright", "source": url, "features": features}
        (output / f"{name}.geojson").write_text(json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{name}: {len(features)} features", flush=True)


if __name__ == "__main__":
    main()
