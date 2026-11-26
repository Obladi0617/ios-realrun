"""Native desktop entry point; --serve exercises the same UI and API without a window."""

import argparse
import ctypes
import importlib.metadata
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from app_info import APP_VERSION, GITHUB_REPOSITORY
from app_settings import data_dir
from desktop_service import DesktopService, ROOT
from desktop_server import DesktopServer


def diagnostics(renderer=False):
    result = {"version": APP_VERSION, "frontend": (ROOT / "frontend" / "web-dist" / "index.html").is_file()}
    try:
        import webview
        result["pywebview"] = importlib.metadata.version("pywebview")
        result["webviewAssets"] = str(Path(webview.__file__).parent / "lib")
        if renderer and sys.platform == "win32":
            from webview.guilib import initialize
            engine = initialize("edgechromium")
            result["renderer"] = getattr(engine, "renderer", "unknown")
            result["rendererLoaded"] = True
    except Exception as error:
        result["error"] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=APP_VERSION)
    parser.add_argument("--serve", action="store_true", help="只启动本机 API 与前端资源服务，不创建窗口")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--connection-file", type=Path)
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--diagnose-renderer", action="store_true", help="只加载原生渲染依赖进行检查，不创建窗口")
    parser.add_argument("--report-file", type=Path, help="把诊断结果保存为 JSON，适用于无控制台 EXE")
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--takeover", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.diagnose or args.diagnose_renderer:
        report = diagnostics(args.diagnose_renderer)
        if args.report_file:
            args.report_file.parent.mkdir(parents=True, exist_ok=True)
            args.report_file.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), flush=True)
        if report.get("error"):
            raise SystemExit(1)
        return
    if args.legacy:
        from launcher import main as legacy_main
        legacy_main()
        return
    assets = ROOT / "frontend" / "web-dist"
    if not (assets / "index.html").is_file():
        raise RuntimeError("前端尚未构建，请先在 frontend 目录执行 npm ci 和 npm run build。")
    service = DesktopService(headless=args.serve)
    server = DesktopServer(service, assets, args.port)
    url = server.start()
    try:
        if args.connection_file:
            args.connection_file.parent.mkdir(parents=True, exist_ok=True)
            args.connection_file.write_text(json.dumps({"url": url, "origin": server.origin, "token": server.token}), encoding="utf-8")
        if args.serve:
            print("RealRun desktop service: " + server.origin, flush=True)
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            while True:
                time.sleep(0.25)
        else:
            from launcher import acquire_gui_instance, activate_existing_instance
            acquired = acquire_gui_instance()
            if args.takeover:
                deadline = time.monotonic() + 15
                while not acquired and time.monotonic() < deadline:
                    time.sleep(0.2)
                    acquired = acquire_gui_instance()
            if not acquired:
                activate_existing_instance()
                return
            import webview
            webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False
            webview.settings["ALLOW_FILE_URLS"] = False
            window = webview.create_window("iOS RealRun · Device Console", url, width=1280, height=900, min_size=(960, 680), background_color="#11161d", text_select=True)
            service.request_close = window.destroy
            map_window = {"window": None}

            def show_map():
                current = map_window["window"]
                if current is not None:
                    current.show()
                    current.restore()
                    return
                current = webview.create_window("RealRun · 实时跑步路径", server.origin + "/?view=map#token=" + server.token,
                                                width=1050, height=800, min_size=(700, 560), background_color="#11161d")
                map_window["window"] = current
                current.events.closed += lambda: map_window.update(window=None)

            def close_windows():
                service.close()
                if map_window["window"] is not None:
                    map_window["window"].destroy()
                window.destroy()

            def on_closing():
                if service.closing:
                    return True
                threading.Thread(target=close_windows, name="realrun-close", daemon=True).start()
                return False

            def elevate():
                if service.thread is not None and service.thread.is_alive():
                    raise ValueError("请先停止当前任务。")
                arguments = ["--takeover"] if getattr(sys, "frozen", False) else [str(ROOT / "desktop_app.py"), "--takeover"]
                shell = ctypes.WinDLL("shell32", use_last_error=True)
                shell.ShellExecuteW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int)
                shell.ShellExecuteW.restype = ctypes.c_void_p
                result = shell.ShellExecuteW(None, "runas", sys.executable, subprocess.list2cmdline(arguments), str(ROOT), 1)
                if not result or result <= 32:
                    raise RuntimeError("管理员启动未完成，当前窗口已保留。")
                threading.Thread(target=close_windows, daemon=True).start()

            service.open_map_window = show_map
            service.elevate = elevate if sys.platform == "win32" else None
            window.events.closing += on_closing

            def choose_apk():
                selected = window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False, file_types=("Android APK (*.apk)",))
                return selected[0] if selected else None

            service.pick_file = choose_apk
            webview.start(gui="edgechromium" if sys.platform == "win32" else None, private_mode=True,
                          user_agent=f"RealRun/{APP_VERSION} (+https://github.com/{GITHUB_REPOSITORY})",
                          storage_path=str(data_dir() / "webview"))
    except KeyboardInterrupt:
        pass
    finally:
        service.close()
        server.close()
        if args.connection_file:
            args.connection_file.unlink(missing_ok=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
