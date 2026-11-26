"""Loopback-only assets and authenticated API for the desktop frontend."""

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import secrets
import threading
import urllib.parse

from map_search import search_places


class DesktopServer:
    def __init__(self, service, assets, port=0):
        self.service = service
        self.assets = Path(assets).resolve()
        self.token = secrets.token_urlsafe(32)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, payload):
                data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def authorized(self):
                origin = self.headers.get("Origin")
                if origin and origin != outer.origin:
                    return False
                return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + outer.token)

            def do_GET(self):
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path.startswith("/api/"):
                    if not self.authorized():
                        return self.reply(403, {"error": "本机访问凭据无效。"})
                    query = urllib.parse.parse_qs(parsed.query)
                    try:
                        if parsed.path == "/api/state":
                            payload = outer.service.snapshot(int(query.get("cursor", [0])[0]), query.get("run", [""])[0], int(query.get("logs", [0])[0]))
                        elif parsed.path == "/api/route":
                            payload = outer.service.route(query.get("name", [outer.service.settings["route"]])[0])
                        elif parsed.path == "/api/place-search":
                            payload = {"places": search_places(query.get("q", [""])[0])}
                        else:
                            return self.reply(404, {"error": "接口不存在。"})
                        return self.reply(200, payload)
                    except (ValueError, OSError) as error:
                        return self.reply(400, {"error": str(error)})
                    except RuntimeError as error:
                        return self.reply(502, {"error": str(error)})
                relative = urllib.parse.unquote(parsed.path).lstrip("/") or "index.html"
                path = (outer.assets / relative).resolve()
                if not path.is_relative_to(outer.assets) or not path.is_file():
                    self.send_error(404)
                    return
                data = path.read_bytes()
                self.send_response(200)
                types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".geojson": "application/geo+json"}
                self.send_header("Content-Type", types.get(path.suffix, mimetypes.guess_type(path.name)[0] or "application/octet-stream"))
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if not self.authorized():
                    return self.reply(403, {"error": "本机访问凭据无效。"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 32768 or self.headers.get_content_type() != "application/json":
                        return self.reply(400, {"error": "请求格式无效。"})
                    payload = json.loads(self.rfile.read(size))
                    if not isinstance(payload, dict):
                        raise ValueError("请求格式无效。")
                    if self.path == "/api/action":
                        result = outer.service.dispatch(payload.get("action"), payload.get("values"))
                    elif self.path == "/api/settings":
                        result = outer.service.save_preferences(payload)
                    else:
                        return self.reply(404, {"error": "接口不存在。"})
                    return self.reply(200, result)
                except (ValueError, OSError, TypeError) as error:
                    return self.reply(400, {"error": str(error)})

        self.http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.http.daemon_threads = True
        self.origin = "http://127.0.0.1:" + str(self.http.server_port)
        self.url = self.origin + "/#token=" + self.token
        self.thread = threading.Thread(target=self.http.serve_forever, name="realrun-http", daemon=True)

    def start(self):
        self.thread.start()
        return self.url

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
