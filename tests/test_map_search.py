import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from map_search import _search_photon, search_places


class PlaceSearchTests(unittest.TestCase):
    def setUp(self):
        _search_photon.cache_clear()
        self.addCleanup(_search_photon.cache_clear)

    def test_decimal_coordinates_need_no_online_search(self):
        with patch("map_search.urlopen") as provider:
            result = search_places("-33.87，151.21")
        self.assertEqual(result[0]["latitude"], -33.87)
        self.assertEqual(result[0]["longitude"], 151.21)
        provider.assert_not_called()

    def test_worldwide_results_use_longitude_latitude_order_and_are_cached(self):
        data = {"features": [
            {"geometry": {"coordinates": [139.76, 35.68]}, "properties": {"name": "Tokyo", "country": "Japan"}},
            {"geometry": {"coordinates": [609, 35.68]}, "properties": {"name": "Invalid"}},
        ]}
        with patch("map_search.urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as provider, \
             patch("map_search.time.sleep"):
            first = search_places("东京 日本")
            second = search_places(" 东京   日本 ")
        self.assertEqual(first, [{"label": "Tokyo · Japan", "longitude": 139.76, "latitude": 35.68}])
        self.assertEqual(second, first)
        provider.assert_called_once()
        request = provider.call_args.args[0]
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)["q"], ["东京 日本"])
