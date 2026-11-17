"""Download verified installers from this project's public GitHub Releases."""

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from app_info import APP_VERSION, GITHUB_REPOSITORY
from app_settings import data_dir


ASSET_NAME = "iOS-RealRun-Setup.exe"
LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
MAX_INSTALLER_BYTES = 512 * 1024 * 1024
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com",
                  "github-releases.githubusercontent.com"}


class UpdateError(RuntimeError):
    pass


def version_tuple(version):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise UpdateError("发布版本号格式无效。")
    return tuple(int(part) for part in match.groups())


@dataclass(frozen=True)
class Update:
    version: str
    url: str
    size: int
    sha256: str


def parse_release(release, current_version=APP_VERSION):
    if not isinstance(release, dict):
        raise UpdateError("GitHub 返回的版本信息无效。")
    if release.get("draft") or release.get("prerelease"):
        return None
    tag = release.get("tag_name", "")
    if not isinstance(tag, str):
        raise UpdateError("发布版本号格式无效。")
    if version_tuple(tag) <= version_tuple(current_version):
        return None
    expected_url = f"https://github.com/{GITHUB_REPOSITORY}/releases/download/{tag}/{ASSET_NAME}"
    for asset in release.get("assets", []):
        if not isinstance(asset, dict) or asset.get("name") != ASSET_NAME or asset.get("state") != "uploaded":
            continue
        size = asset.get("size")
        digest = asset.get("digest") or ""
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_INSTALLER_BYTES:
            raise UpdateError("安装包大小无效。")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise UpdateError("此版本缺少 SHA256 校验值，无法安全安装。")
        if asset.get("browser_download_url") != expected_url:
            raise UpdateError("安装包链接不属于本项目的 GitHub Release。")
        return Update(tag.removeprefix("v"), expected_url, size, digest[7:].lower())
    raise UpdateError("新版本尚未提供可用的 Windows 安装包，请稍后重试。")


class ReleaseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_download_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in DOWNLOAD_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise UpdateError("安装包下载被重定向到未经允许的地址。")


def latest_update(current_version=APP_VERSION):
    request = urllib.request.Request(LATEST_URL, headers={
        "User-Agent": f"iOSRealRun/{APP_VERSION}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise UpdateError("GitHub 版本信息过大。")
        return parse_release(json.loads(payload), current_version)
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise UpdateError("GitHub 请求过于频繁，请稍后重试。") from error
        raise UpdateError(f"获取版本信息失败（HTTP {error.code}）。") from error
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise UpdateError("无法连接 GitHub，请检查网络后重试。") from error


def download_update(update, directory=None, progress=None):
    validate_download_url(update.url)
    version_tuple(update.version)
    if not re.fullmatch(r"[0-9a-f]{64}", update.sha256) or not 0 < update.size <= MAX_INSTALLER_BYTES:
        raise UpdateError("安装包校验信息无效。")
    target_dir = Path(directory) if directory else data_dir() / "updates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"iOS-RealRun-{update.version}-Setup.exe"
    fd, temporary = tempfile.mkstemp(prefix="download-", suffix=".part", dir=target_dir)
    downloaded = 0
    digest = hashlib.sha256()
    last_progress = 0.0
    opener = urllib.request.build_opener(ReleaseRedirects())
    request = urllib.request.Request(update.url, headers={"User-Agent": f"iOSRealRun/{APP_VERSION}"})
    try:
        with os.fdopen(fd, "wb") as output:
            with opener.open(request, timeout=30) as response:
                validate_download_url(response.geturl())
                while chunk := response.read(256 * 1024):
                    downloaded += len(chunk)
                    if downloaded > update.size:
                        raise UpdateError("下载内容超过安装包声明的大小。")
                    output.write(chunk)
                    digest.update(chunk)
                    if progress and time.monotonic() - last_progress > 0.5:
                        progress(downloaded, update.size)
                        last_progress = time.monotonic()
        if downloaded != update.size or not hmac.compare_digest(digest.hexdigest(), update.sha256):
            raise UpdateError("安装包校验失败，请重新下载。")
        os.replace(temporary, target)
        if progress:
            progress(downloaded, update.size)
        return target
    except (OSError, urllib.error.URLError) as error:
        raise UpdateError("安装包下载失败，请检查网络后重试。") from error
    finally:
        Path(temporary).unlink(missing_ok=True)
