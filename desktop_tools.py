"""App downloads and an official, verified scrcpy runtime for the desktop shell."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import urllib.parse
import urllib.request
import zipfile

from app_info import APP_VERSION
from app_settings import data_dir
from session_control import raise_if_stopped


APPS = {
    "tyys": {"name": "浙大体艺", "package": "net.crigh.mysport",
             "activity": "net.crigh.cgsport.ui.activity.ZdSplashActivity",
             "certificate": "0bd006a62fdbcc4da28432e869b19126832f17f6c88056ca2f3dfc4bb0d89f71"},
    "ding": {"name": "钉钉", "package": "com.alibaba.android.rimet",
             "activity": "com.alibaba.android.rimet.biz.LaunchHomeActivity",
             "certificate": "a680d36e6014d4d7b5ec64dc79b576ebe96a48c6dca9121355c946c900e926f2"},
}
ANDROID_AGENT = "Mozilla/5.0 (Linux; Android 15; Pixel 5) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36"


def _length_value(data, offset=0):
    if offset + 4 > len(data):
        raise ValueError("APK 签名数据不完整。")
    size = struct.unpack_from("<I", data, offset)[0]
    end = offset + 4 + size
    if end > len(data):
        raise ValueError("APK 签名数据不完整。")
    return data[offset + 4:end], end


def apk_certificate(path):
    """Read the v2/v3 signing certificate. Android verifies the signatures on install."""
    with zipfile.ZipFile(path) as archive:
        if "AndroidManifest.xml" not in archive.namelist():
            raise ValueError("文件不是有效的 Android APK。")
    with Path(path).open("rb") as source:
        source.seek(0, 2)
        length = source.tell()
        source.seek(max(0, length - 65557))
        tail = source.read()
        end = tail.rfind(b"PK\x05\x06")
        if end < 0 or end + 22 > len(tail):
            raise ValueError("APK 目录数据无效。")
        directory = struct.unpack_from("<I", tail, end + 16)[0]
        if directory < 24:
            raise ValueError("APK 缺少 v2/v3 签名。")
        source.seek(directory - 24)
        footer = source.read(24)
        if footer[8:] != b"APK Sig Block 42":
            raise ValueError("APK 缺少 v2/v3 签名。")
        block_size = struct.unpack_from("<Q", footer)[0]
        if not 24 <= block_size <= min(directory - 8, 16 * 1024 * 1024):
            raise ValueError("APK 签名块大小无效。")
        source.seek(directory - block_size - 8)
        block = source.read(block_size + 8)
        if struct.unpack_from("<Q", block)[0] != block_size:
            raise ValueError("APK 签名块无效。")
    offset = 8
    while offset < len(block) - 24:
        size = struct.unpack_from("<Q", block, offset)[0]
        if size < 4 or offset + 8 + size > len(block) - 24:
            raise ValueError("APK 签名条目无效。")
        identifier = struct.unpack_from("<I", block, offset + 8)[0]
        if identifier in (0x7109871A, 0xF05368C0, 0x1B93AD61):
            signers, _ = _length_value(block[offset + 12:offset + 8 + size])
            signer, _ = _length_value(signers)
            signed_data, _ = _length_value(signer)
            _, next_offset = _length_value(signed_data)
            certificates, _ = _length_value(signed_data, next_offset)
            certificate, _ = _length_value(certificates)
            return hashlib.sha256(certificate).hexdigest()
        offset += 8 + size
    raise ValueError("APK 未提供支持的签名。")


class DownloadRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, validate):
        self.validate = validate

    def redirect_request(self, request, fp, code, message, headers, new_url):
        self.validate(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


def _github_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com"} or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("工具下载地址无效。")


def _app_url(key, url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    if parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        raise ValueError("APK 下载地址无效。")
    if key == "tyys":
        valid = host == "tyys.zju.edu.cn" and parsed.scheme in ("http", "https") and parsed.path.startswith("/cgapp-server/")
    else:
        valid = parsed.scheme == "https" and any(host == suffix or host.endswith("." + suffix) for suffix in ("dingtalk.com", "alicdn.com", "aliyuncs.com"))
    if not valid:
        raise ValueError("APK 下载没有指向已知官方站点。")


def download_file(url, target, validator, progress=None, expected_hash=None, expected_size=None, validate_file=None):
    validator(url)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(DownloadRedirects(validator))
    request = urllib.request.Request(url, headers={"User-Agent": ANDROID_AGENT, "Referer": "https://www.dingtalk.com/download"})
    fd, temporary = tempfile.mkstemp(prefix="download-", suffix=".part", dir=target.parent)
    count, digest = 0, hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as output, opener.open(request, timeout=30) as response:
            validator(response.geturl())
            declared = int(response.headers.get("Content-Length") or 0)
            limit = expected_size or 512 * 1024 * 1024
            if declared > limit:
                raise ValueError("下载文件大小超出限制。")
            while chunk := response.read(256 * 1024):
                raise_if_stopped()
                count += len(chunk)
                if count > limit:
                    raise ValueError("下载文件大小超出限制。")
                output.write(chunk)
                digest.update(chunk)
                if progress:
                    progress(count, expected_size or declared)
        if expected_size and count != expected_size or declared and count != declared:
            raise ValueError("下载文件不完整。")
        if expected_hash and digest.hexdigest() != expected_hash:
            raise ValueError("下载文件 SHA256 校验失败。")
        if validate_file:
            validate_file(Path(temporary))
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def download_app(key, progress=None):
    if key not in APPS:
        raise ValueError("未知应用。")
    url = "https://www.dingtalk.com/android/d/"
    if key == "tyys":
        request = urllib.request.Request("http://tyys.zju.edu.cn/cgapp-server/qrcode/download", headers={"User-Agent": ANDROID_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            page = response.read(512 * 1024).decode("utf-8")
        match = re.search(r'href=["\']([^"\']+\.apk)["\']', page, re.I)
        if not match:
            raise RuntimeError("学校下载入口暂未提供 APK，请稍后重试。")
        url = urllib.parse.urljoin("http://tyys.zju.edu.cn", match[1])
        parts = urllib.parse.urlsplit(url)
        url = urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/")))
    target = data_dir() / "downloads" / ("tyys.apk" if key == "tyys" else "dingtalk.apk")

    def verify(path):
        if apk_certificate(path) != APPS[key]["certificate"]:
            raise ValueError("APK 签名证书与已核对的官方版本不一致，已停止安装。")

    return download_file(url, target, lambda link: _app_url(key, link), progress, validate_file=verify)


def find_scrcpy(configured=""):
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return path.resolve()
        raise ValueError("手机窗口工具路径不存在。")
    metadata = data_dir() / "tools" / "scrcpy.json"
    try:
        path = Path(json.loads(metadata.read_text(encoding="utf-8"))["path"])
        if path.is_file() and path.resolve().is_relative_to((data_dir() / "tools").resolve()):
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    found = shutil.which("scrcpy")
    return Path(found) if found else None


def ensure_scrcpy(progress=None, configured=""):
    found = find_scrcpy(configured)
    if found:
        return found
    request = urllib.request.Request("https://api.github.com/repos/Genymobile/scrcpy/releases/latest", headers={"User-Agent": f"RealRun/{APP_VERSION}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.loads(response.read(1024 * 1024))
    version = release.get("tag_name", "")
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        raise ValueError("手机窗口工具版本信息无效。")
    name = f"scrcpy-win64-{version}.zip"
    asset = next((item for item in release.get("assets", []) if item.get("name") == name), None)
    if not asset or not re.fullmatch(r"sha256:[a-f0-9]{64}", asset.get("digest") or ""):
        raise ValueError("手机窗口工具缺少下载校验信息。")
    expected_url = f"https://github.com/Genymobile/scrcpy/releases/download/{version}/{name}"
    if asset.get("browser_download_url") != expected_url or not 0 < asset.get("size", 0) < 150 * 1024 * 1024:
        raise ValueError("手机窗口工具下载信息无效。")
    tools = data_dir() / "tools"
    archive = download_file(expected_url, tools / name, _github_url, progress, asset["digest"][7:], asset["size"])
    destination = (tools / version).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 1000 or sum(item.file_size for item in entries) > 512 * 1024 * 1024:
            raise ValueError("手机窗口工具压缩包大小异常。")
        for item in entries:
            path = (destination / item.filename).resolve()
            if not path.is_relative_to(destination) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("手机窗口工具压缩包路径无效。")
        source.extractall(destination)
    executables = list(destination.rglob("scrcpy.exe"))
    if len(executables) != 1:
        raise ValueError("手机窗口工具压缩包内容无效。")
    metadata = tools / "scrcpy.json"
    metadata.write_text(json.dumps({"version": version, "path": str(executables[0])}), encoding="utf-8")
    return executables[0]
