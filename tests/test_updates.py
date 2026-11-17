import copy
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_update import ASSET_NAME, GITHUB_REPOSITORY, UpdateError, download_update, parse_release, validate_download_url


PAYLOAD = b"installer fixture"


def release(version="v99.0.0"):
    return {
        "tag_name": version, "draft": False, "prerelease": False,
        "assets": [{"name": ASSET_NAME, "state": "uploaded", "size": len(PAYLOAD),
                    "digest": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest(),
                    "browser_download_url": f"https://github.com/{GITHUB_REPOSITORY}/releases/download/{version}/{ASSET_NAME}"}],
    }


class DownloadResponse(io.BytesIO):
    def geturl(self):
        return "https://release-assets.githubusercontent.com/test"


class UpdatesTests(unittest.TestCase):
    def test_only_new_stable_release(self):
        self.assertIsNotNone(parse_release(release("v1.10.0"), "1.9.9"))
        self.assertIsNone(parse_release(release("v1.3.0"), "1.3.0"))
        preview = release()
        preview["prerelease"] = True
        self.assertIsNone(parse_release(preview))

    def test_untrusted_asset_and_missing_hash_are_rejected(self):
        for field, value in (("browser_download_url", "https://example.com/install.exe"),
                             ("digest", None), ("size", 0)):
            with self.subTest(field=field):
                data = copy.deepcopy(release())
                data["assets"][0][field] = value
                with self.assertRaises(UpdateError):
                    parse_release(data)

    def test_redirects_must_stay_on_https_github_asset_hosts(self):
        for url in ("http://github.com/file", "https://github.com.attacker.test/file", "https://localhost/file",
                    "https://user:pass@github.com/file"):
            with self.subTest(url=url), self.assertRaises(UpdateError):
                validate_download_url(url)

    def download(self, body, directory):
        with patch("app_update.urllib.request.build_opener") as opener:
            opener.return_value.open.return_value = DownloadResponse(body)
            return download_update(parse_release(release()), directory=directory)

    def test_verified_download_is_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.download(PAYLOAD, directory)
            self.assertEqual(result.read_bytes(), PAYLOAD)
            self.assertEqual(list(Path(directory).glob("*.part")), [])

    def test_corrupt_truncated_and_oversized_downloads_are_removed(self):
        for body in (PAYLOAD[:-1], b"X" * len(PAYLOAD), PAYLOAD + b"extra"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(UpdateError):
                    self.download(body, directory)
                self.assertEqual(list(Path(directory).iterdir()), [])
