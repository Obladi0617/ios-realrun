import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import ctypes
import multiprocessing
from ctypes import wintypes
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from app_info import APP_VERSION
from app_settings import ROUTES, load_settings, save_settings, validate_run
from session_control import STOP_FILE_ENV
from external_process import external_popen


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else BASE_DIR
STOP_FLAG = Path(tempfile.gettempdir()) / "ios-realrun-stop.flag"
LOG_FILE = Path(tempfile.gettempdir()) / "ios-realrun-gui.log"

WINDOW_TITLE = "iOS RealRun · Device Console"
SW_RESTORE = 9
ERROR_ALREADY_EXISTS = 183

VARIATION_PROFILES = {
    "匀速": "constant",
    "平稳": "steady",
    "业余跑者": "recreational",
    "波动较大": "variable",
}
BACKENDS = {"iPhone / iPad（USB）": "ios", "Android 模拟器（APK）": "android"}

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
LOGGER_PREFIX = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}[^-]*-\s*)?"
    r"(?:BookOfSaturday\s+)?(?:[\w.]+\[\d+\]\s+)?"
    r"(?:INFO|WARNING|ERROR|DEBUG)\s*-\s*"
)

if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.FindWindowW.restype = wintypes.HWND
    _user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    _user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    _user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL
else:
    _user32 = None
    _kernel32 = None

_gui_mutex = None


def acquire_gui_instance() -> bool:
    """Return False when another instance already owns the single-instance lock."""
    global _gui_mutex
    if _kernel32 is None:
        return True
    _gui_mutex = _kernel32.CreateMutexW(None, False, "Local\\iOSRealRunGui")
    if not _gui_mutex:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(_gui_mutex)
        _gui_mutex = None
        return False
    return True

def activate_existing_instance() -> bool:
    """Bring an existing iOS RealRun window to the front.

    Returns True when a window already exists, in which case this process should exit.
    """
    if _user32 is None:
        return False
    hwnd = _user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.SetForegroundWindow(hwnd)
    return True


def request_stop() -> None:
    try:
        STOP_FLAG.write_text("stop", encoding="utf-8")
    except OSError:
        pass


def clear_stop_flag() -> None:
    try:
        STOP_FLAG.unlink(missing_ok=True)
    except OSError:
        pass


class RunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry("860x780")
        self.root.minsize(820, 680)
        self.root.configure(bg="#11161d")
        self.output_queue = queue.Queue()
        self.process = None
        self.action_process = None
        self.settings = load_settings()
        self.task_name = ""
        self.stopping = False
        self.closing = False
        self.updating = False
        self.controls = []
        self.setup_style()
        self.build_ui()
        self.root.after(100, self.consume_output)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#11161d")
        style.configure("Panel.TFrame", background="#1a222c")
        style.configure("TLabel", background="#11161d", foreground="#d9e1e8", font=("Bahnschrift", 10))
        style.configure("Panel.TLabel", background="#1a222c", foreground="#d9e1e8", font=("Bahnschrift", 10))
        style.configure("Title.TLabel", background="#11161d", foreground="#f4f7f9", font=("Bahnschrift", 22, "bold"))
        style.configure("Muted.TLabel", background="#11161d", foreground="#84919d", font=("Bahnschrift", 9))
        style.configure("Status.TLabel", background="#1a222c", foreground="#f2b84b", font=("Bahnschrift", 10, "bold"))
        style.configure("TButton", background="#2a3541", foreground="#f4f7f9", borderwidth=0, padding=(14, 8), font=("Bahnschrift", 10, "bold"))
        style.map("TButton", background=[("active", "#3b4b5b")])
        style.configure("Accent.TButton", background="#d9912b", foreground="#11161d")
        style.map("Accent.TButton", background=[("active", "#f2b84b")])
        style.configure("Danger.TButton", background="#7f3c3c", foreground="#fff4f0")
        style.map("Danger.TButton", background=[("active", "#a44d4d")])
        style.configure("TEntry", fieldbackground="#10161d", foreground="#f4f7f9", insertcolor="#f2b84b")
        style.configure("TCombobox", fieldbackground="#10161d", foreground="#f4f7f9", arrowsize=16)

    def build_ui(self):
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=28, pady=(24, 12))
        ttk.Label(header, text="iOS RealRun", style="Title.TLabel").pack(side="left")
        self.update_button = ttk.Button(header, text="检查更新", command=self.check_update)
        self.update_button.pack(side="right")
        ttk.Label(header, text=f"v{APP_VERSION}", style="Muted.TLabel").pack(side="right", padx=12)

        backend_row = ttk.Frame(self.root)
        backend_row.pack(fill="x", padx=28)
        self.backend = tk.StringVar(value=next(label for label, value in BACKENDS.items() if value == self.settings["backend"]))
        backend_box = ttk.Combobox(backend_row, textvariable=self.backend, values=tuple(BACKENDS), state="readonly", width=28)
        backend_box.pack(side="left")
        self.controls.append((backend_box, "readonly"))
        backend_box.bind("<<ComboboxSelected>>", self.change_backend)
        self.backend_hint = ttk.Label(backend_row, style="Muted.TLabel")
        self.backend_hint.pack(side="left", padx=12)

        panel = ttk.Frame(self.root, style="Panel.TFrame", padding=20)
        panel.pack(fill="x", padx=28, pady=8)
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="路线", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16), pady=7)
        self.route = tk.StringVar(value=self.settings["route"])
        route_box = ttk.Combobox(panel, textvariable=self.route, values=ROUTES, state="readonly")
        route_box.grid(row=0, column=1, sticky="ew", pady=7)
        self.controls.append((route_box, "readonly"))
        ttk.Label(panel, text="速度 (m/s)", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=7)
        self.speed = tk.StringVar(value=self.settings["speed"])
        speed_entry = ttk.Entry(panel, textvariable=self.speed)
        speed_entry.grid(row=1, column=1, sticky="ew", pady=7)
        self.controls.append((speed_entry, "normal"))
        ttk.Label(panel, text="运行时长", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 16), pady=7)
        self.duration = tk.StringVar(value=self.settings["minutes"])
        duration_box = ttk.Combobox(panel, textvariable=self.duration, values=("10", "20", "30", "45", "60", "0"))
        duration_box.grid(row=2, column=1, sticky="ew", pady=7)
        self.controls.append((duration_box, "normal"))
        ttk.Label(panel, text="分钟，0 表示仅按目标里程停止", style="Panel.TLabel").grid(row=2, column=2, sticky="w", padx=(12, 0), pady=7)
        ttk.Label(panel, text="配速波动", style="Panel.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 16), pady=7)
        self.profile = tk.StringVar(value=next(label for label, value in VARIATION_PROFILES.items() if value == self.settings["profile"]))
        profile_box = ttk.Combobox(panel, textvariable=self.profile, values=tuple(VARIATION_PROFILES), state="readonly")
        profile_box.grid(row=3, column=1, sticky="ew", pady=7)
        self.controls.append((profile_box, "readonly"))
        ttk.Label(panel, text="模拟真人速度起伏", style="Panel.TLabel").grid(row=3, column=2, sticky="w", padx=(12, 0), pady=7)

        self.android_panel = ttk.Frame(panel, style="Panel.TFrame")
        self.android_panel.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.android_panel.columnconfigure(1, weight=1)
        self.sdk = tk.StringVar(value=self.settings["sdk"])
        self.avd = tk.StringVar(value=self.settings["avd"])
        self.serial = tk.StringVar(value=self.settings["serial"])
        for row, (label, variable) in enumerate((("Android SDK", self.sdk), ("AVD 名称", self.avd), ("设备编号", self.serial))):
            ttk.Label(self.android_panel, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 16), pady=4)
            entry = ttk.Entry(self.android_panel, textvariable=variable)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            self.controls.append((entry, "normal"))
        self.sdk_button = ttk.Button(self.android_panel, text="选择目录", command=self.choose_sdk)
        self.sdk_button.grid(row=0, column=2, padx=(12, 0))
        ttk.Label(self.android_panel, text="启动前填写虚拟设备名称", style="Panel.TLabel").grid(row=1, column=2, padx=(12, 0))
        ttk.Label(self.android_panel, text="留空自动选择唯一模拟器", style="Panel.TLabel").grid(row=2, column=2, padx=(12, 0))

        actions = ttk.Frame(self.root)
        actions.pack(fill="x", padx=28, pady=(8, 4))
        self.check_button = ttk.Button(actions, text="检查设备", command=self.check_device)
        self.check_button.pack(side="left", padx=(0, 8))
        self.mount_button = ttk.Button(actions, text="挂载开发者镜像", command=self.mount_image)
        self.mount_button.pack(side="left", padx=8)
        self.start_button = ttk.Button(actions, text="开始模拟", style="Accent.TButton", command=self.start_run)
        self.start_button.pack(side="right", padx=(8, 0))
        self.stop_button = ttk.Button(actions, text="停止", style="Danger.TButton", command=self.stop_run, state="disabled")
        self.stop_button.pack(side="right")

        self.android_actions = ttk.Frame(self.root)
        self.android_actions.pack(fill="x", padx=28, pady=4)
        self.list_button = ttk.Button(self.android_actions, text="列出虚拟设备", command=lambda: self.execute(("--list-android",), action=True, name="列出虚拟设备"))
        self.list_button.pack(side="left")
        self.emulator_button = ttk.Button(self.android_actions, text="启动模拟器", command=lambda: self.execute(("--start-emulator", "--avd", self.avd.get().strip()), action=True, name="启动模拟器"))
        self.emulator_button.pack(side="left", padx=8)
        self.apk_button = ttk.Button(self.android_actions, text="安装 APK", command=self.install_apk)
        self.apk_button.pack(side="left")

        status_panel = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 10))
        status_panel.pack(fill="x", padx=28, pady=(8, 4))
        ttk.Label(status_panel, text="状态", style="Panel.TLabel").pack(side="left")
        self.status = tk.StringVar(value="等待设备")
        ttk.Label(status_panel, textvariable=self.status, style="Status.TLabel").pack(side="right")

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=28, pady=(8, 24))
        log_header = ttk.Frame(log_frame)
        log_header.pack(fill="x", pady=(0, 6))
        ttk.Label(log_header, text="运行日志", style="Muted.TLabel").pack(side="left")
        ttk.Button(log_header, text="清空", command=self.clear_log).pack(side="right")
        self.log = scrolledtext.ScrolledText(log_frame, height=12, bg="#0c1117", fg="#b8c7d3", insertbackground="#f2b84b", relief="flat", borderwidth=0, font=("Cascadia Mono", 9), padx=12, pady=10)
        self.log.pack(fill="both", expand=True)
        self.change_backend()
        self.write_log("控制台已就绪。选择设备类型，再点击“检查设备”。")

    def is_android(self):
        return BACKENDS[self.backend.get()] == "android"

    def change_backend(self, _event=None):
        if self.is_android():
            self.android_panel.grid()
            self.android_actions.pack(after=self.mount_button.master, fill="x", padx=28, pady=4)
            self.mount_button.pack_forget()
            self.backend_hint.configure(text="在电脑内运行 APK，需安装官方 Android Emulator")
        else:
            self.android_panel.grid_remove()
            self.android_actions.pack_forget()
            self.mount_button.pack(side="left", padx=8)
            self.backend_hint.configure(text="连接一台已解锁并信任电脑的 iOS 设备")

    def choose_sdk(self):
        path = filedialog.askdirectory(title="选择 Android SDK 目录")
        if path:
            self.sdk.set(path)

    def install_apk(self):
        path = filedialog.askopenfilename(title="选择 Android APK", filetypes=[("Android 安装包", "*.apk")])
        if path:
            self.execute(("--install-apk", path), action=True, name="安装 APK")

    def save_preferences(self):
        try:
            save_settings({"backend": BACKENDS[self.backend.get()], "route": self.route.get(),
                           "speed": self.speed.get(), "minutes": self.duration.get(),
                           "profile": VARIATION_PROFILES[self.profile.get()], "sdk": self.sdk.get().strip(),
                           "serial": self.serial.get().strip(), "avd": self.avd.get().strip()})
        except OSError as error:
            self.write_log(f"保存设置失败：{error}")

    def worker_command(self, *args):
        if getattr(sys, "frozen", False):
            worker = APP_DIR / "iOSRealRun-worker.exe"
            if worker.exists():
                return [str(worker), *args]
            raise RuntimeError("缺少 iOSRealRun-worker.exe，请重新安装完整安装包。")
        return [sys.executable, str(BASE_DIR / "worker.py"), *args]

    @staticmethod
    def format_log_line(text):
        line = ANSI_ESCAPE.sub("", text).strip()
        if not line:
            return ""
        line = LOGGER_PREFIX.sub("", line)
        if "tunnel worker starting" in line:
            return "正在启动设备隧道..."
        if "tunnel command:" in line:
            return "隧道组件已启动"
        if "Tunnel started" in line:
            return "隧道进程已启动"
        if "tunnel created" in line:
            return "设备隧道已建立"
        if "RSD Address:" in line:
            return "隧道地址：" + line.split("RSD Address:", 1)[1].strip()
        if re.match(r"^[0-9a-f:]+\s+\d+$", line):
            address, port = line.rsplit(maxsplit=1)
            return f"隧道地址：{address}，端口：{port}"
        if "init done" in line:
            return "设备初始化完成"
        if "trying to start tunnel" in line:
            return "正在建立设备隧道..."
        if "got route from" in line:
            return "路线已加载：" + line.split("got route from", 1)[1].strip()
        if "Your system version is" in line:
            return "设备系统版本：" + line.split("Your system version is", 1)[1].strip()
        if "DTX reader exiting" in line:
            return "设备连接中断：" + line.split("DTX reader exiting", 1)[1].strip()
        if "Channel is closed" in line or "connection is closed" in line:
            return "设备连接已关闭，无法继续发送定位"
        if line.startswith("[进程结束，退出码 "):
            return line.replace("[进程结束，退出码 ", "任务结束，退出码 ").rstrip("]")
        return line

    def write_log(self, text):
        display_text = self.format_log_line(text)
        if not display_text:
            return
        self.log.insert("end", display_text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 2000:
            self.log.delete("1.0", "101.0")
        self.log.see("end")
        try:
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2 * 1024 * 1024:
                LOG_FILE.replace(LOG_FILE.with_suffix(".previous.log"))
            with LOG_FILE.open("a", encoding="utf-8") as handle:
                handle.write(f"[{time.strftime('%H:%M:%S')}] {display_text}\n")
        except OSError:
            pass

    def clear_log(self):
        self.log.delete("1.0", "end")
        self.write_log("日志已清空。")

    def active_process(self):
        return self.process or self.action_process

    def refresh_buttons(self):
        busy = self.active_process() is not None or self.updating or self.closing
        for button in (self.check_button, self.mount_button, self.start_button, self.list_button,
                       self.emulator_button, self.apk_button, self.sdk_button, self.update_button):
            button.configure(state="disabled" if busy else "normal")
        for widget, normal_state in self.controls:
            widget.configure(state="disabled" if busy else normal_state)
        self.stop_button.configure(state="normal" if self.active_process() and not self.stopping else "disabled")

    def execute(self, args, action=False, name="模拟"):
        if self.active_process() or self.updating or self.closing:
            return
        clear_stop_flag()
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        environment[STOP_FILE_ENV] = str(STOP_FLAG)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        backend_args = ("--backend", "android", "--sdk", self.sdk.get().strip(), "--serial", self.serial.get().strip()) if self.is_android() else ()
        try:
            process = subprocess.Popen(self.worker_command(*args, *backend_args), cwd=APP_DIR,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace", env=environment, creationflags=flags)
        except (OSError, RuntimeError) as error:
            self.write_log(f"启动失败：{error}")
            self.status.set("启动失败")
            return
        if action:
            self.action_process = process
        else:
            self.process = process
        self.task_name = name
        self.stopping = False
        self.status.set(name + "中")
        self.save_preferences()
        self.refresh_buttons()
        threading.Thread(target=self.read_process, args=(process,), daemon=True).start()

    def read_process(self, process):
        try:
            for line in process.stdout:
                self.output_queue.put(("line", process, line))
        finally:
            process.stdout.close()
            self.output_queue.put(("done", process, process.wait()))

    def consume_output(self):
        while True:
            try:
                kind, source, value = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self.write_log(value)
            elif kind == "done" and source is self.active_process():
                self.write_log(f"任务结束，退出码 {value}")
                was_run = source is self.process
                self.process = self.action_process = None
                if value != 0:
                    self.status.set("操作失败，请查看日志")
                elif self.stopping or was_run:
                    self.status.set("已停止")
                else:
                    self.status.set(self.task_name + "完成")
                self.stopping = False
                clear_stop_flag()
                self.refresh_buttons()
                if self.closing:
                    self.root.destroy()
                    return
            elif kind == "update_checked":
                self.offer_update(value)
            elif kind == "update_error":
                self.updating = False
                self.update_button.configure(text="检查更新")
                self.refresh_buttons()
                self.write_log(f"更新失败：{value}")
                messagebox.showerror("更新失败", value)
            elif kind == "update_progress":
                self.update_button.configure(text=f"下载 {value}%")
            elif kind == "update_ready":
                self.finish_update(value)
        self.root.after(100, self.consume_output)

    def check_device(self):
        self.write_log("正在检查设备连接...")
        self.execute(("--check",), action=True, name="检查设备")

    def mount_image(self):
        self.write_log("正在挂载开发者镜像...")
        self.execute(("--mount",), action=True, name="挂载镜像")

    def start_run(self):
        try:
            speed, minutes = validate_run(self.speed.get(), self.duration.get())
        except (ValueError, OverflowError):
            messagebox.showerror("配置错误", "速度范围为 0.1–100 m/s，时长必须是非负整数。")
            return
        profile = VARIATION_PROFILES.get(self.profile.get(), "recreational")
        self.write_log(f"开始模拟：{self.route.get()} / {speed:g} m/s / {minutes} 分钟 / 波动 {self.profile.get()}")
        self.execute(("--run", "--route", self.route.get(), "--speed", str(speed), "--minutes", str(minutes), "--profile", profile))

    @staticmethod
    def force_kill(pid: int) -> None:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            pass

    def stop_run(self, wait_seconds: float = 25.0) -> None:
        """Ask the worker to stop gracefully so the real GPS location is restored."""
        process = self.active_process()
        if not process or self.stopping:
            return
        self.stopping = True
        self.status.set("正在停止")
        self.refresh_buttons()
        self.write_log("正在停止任务..." if self.is_android() else "正在停止任务，运行中的模拟会恢复真实定位...")
        request_stop()

        def wait_for_stop():
            try:
                process.wait(timeout=wait_seconds)
            except subprocess.TimeoutExpired:
                self.output_queue.put(("line", process, "任务未在超时内退出，强制结束进程。"))
                if sys.platform == "win32":
                    self.force_kill(process.pid)
                else:
                    process.kill()

        threading.Thread(target=wait_for_stop, daemon=True).start()

    def check_update(self):
        if self.active_process() or self.updating:
            return
        self.updating = True
        self.update_button.configure(text="正在检查")
        self.refresh_buttons()

        def check():
            from app_update import latest_update

            try:
                self.output_queue.put(("update_checked", None, latest_update()))
            except Exception as error:
                self.output_queue.put(("update_error", None, str(error)))

        threading.Thread(target=check, daemon=True).start()

    def offer_update(self, update):
        if update is None:
            self.updating = False
            self.update_button.configure(text="检查更新")
            self.refresh_buttons()
            messagebox.showinfo("检查更新", f"当前 v{APP_VERSION}，没有更新的正式版本。")
            return
        if not messagebox.askyesno("发现新版本", f"发现 v{update.version}（{update.size / 1024 / 1024:.1f} MB）。\n是否下载安装包？下载后将验证 SHA256。"):
            self.updating = False
            self.update_button.configure(text="检查更新")
            self.refresh_buttons()
            return
        self.update_button.configure(text="下载 0%")

        def download():
            from app_update import download_update

            try:
                path = download_update(update, progress=lambda done, total: self.output_queue.put(("update_progress", None, int(done * 100 / total))))
                self.output_queue.put(("update_ready", None, path))
            except Exception as error:
                self.output_queue.put(("update_error", None, str(error)))

        threading.Thread(target=download, daemon=True).start()

    def finish_update(self, path):
        self.updating = False
        self.update_button.configure(text="检查更新")
        self.refresh_buttons()
        self.write_log(f"安装包已下载并通过 SHA256 校验：{path}")
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("下载完成", f"当前从源码运行，安装包已保存到：\n{path}")
            return
        if messagebox.askyesno("准备安装", "安装包已验证。现在关闭程序并启动新版安装向导吗？"):
            try:
                external_popen([str(path), f"/DIR={APP_DIR}", "/NORESTART"])
            except OSError as error:
                messagebox.showerror("启动安装失败", str(error))
                return
            self.save_preferences()
            self.root.destroy()

    def close(self):
        if self.closing:
            return
        if self.active_process():
            prompt = "任务仍在运行，退出前会先停止任务。确定退出吗？" if self.is_android() else "任务仍在运行，退出前会停止任务并清除运行中的模拟定位。确定退出吗？"
            if not messagebox.askyesno("确认退出", prompt):
                return
            self.closing = True
            self.stop_run()
            self.refresh_buttons()
            return
        self.save_preferences()
        clear_stop_flag()
        self.root.destroy()


def main():
    multiprocessing.freeze_support()
    if activate_existing_instance():
        raise SystemExit
    if not acquire_gui_instance():
        activate_existing_instance()
        raise SystemExit
    app_root = tk.Tk()
    RunnerApp(app_root)
    app_root.mainloop()


if __name__ == "__main__":
    main()
