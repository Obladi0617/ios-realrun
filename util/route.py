import ast
import json


class FixedRoute(list):
    """Track coordinates in WGS84 that should stay on the same line each lap."""


def parse_route(content):
    tmp = ast.literal_eval("[{}]".format(content))
    for i in tmp:
        i["lat"] = float(i["lat"])
        i["lng"] = float(i["lng"])
    return tmp


def load_route(path):
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() != ".geojson":
        return parse_route(content)

    geometry = json.loads(content)["geometry"]
    if geometry["type"] != "LineString":
        raise ValueError("路线需要使用 GeoJSON LineString。")
    points = FixedRoute()
    for longitude, latitude in geometry["coordinates"]:
        lat, lng = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("路线坐标超出有效范围。")
        points.append({"lat": lat, "lng": lng})
    if len(points) < 2:
        raise ValueError("路线至少需要两个坐标点。")
    return points
