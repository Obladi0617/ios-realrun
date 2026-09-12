import os
import queue
import signal
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk


BASE_DIR = Path(__file__).resolve().parent
WORKER = BASE_DIR / "iOSRealRun-worker.exe"


class RunnerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iOS RealRun · Device Console")
        self.root.geometry("760x600")
        self.root.minsize(680, 520)
        self.root.configure(bg="#11161d")
        self.output_queue = queue.Queue()
        self.process = None
        self.action_process = None
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
        ttk.Label(header, text="iOS RealRun", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="iOS 26 虚拟定位控制台  /  DEVICE RUNNER", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))

        panel = ttk.Frame(self.root, style="Panel.TFrame", padding=20)
        panel.pack(fill="x", padx=28, pady=8)
        panel.columnconfigure(1, weight=1)
        ttk.Label(panel, text="路线", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16), pady=7)
        self.route = tk.StringVar(value="ZJGroute.txt")
        route_box = ttk.Combobox(panel, textvariable=self.route, values=("ZJGroute.txt", "YQroute.txt", "HNroute.txt"), state="readonly")
        route_box.grid(row=0, column=1, sticky="ew", pady=7)
        ttk.Label(panel, text="速度 (m/s)", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=7)
        self.speed = tk.StringVar(value="4.8")
        ttk.Entry(panel, textvariable=self.speed).grid(row=1, column=1, sticky="ew", pady=7)
        ttk.Label(panel, text="运行时长", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 16), pady=7)
        self.duration = tk.StringVar(value="30")
        ttk.Combobox(panel, textvariable=self.duration, values=("10", "20", "30", "45", "60", "0"), state="readonly").grid(row=2, column=1, sticky="ew", pady=7)
        ttk.Label(panel, text="分钟，0 表示手动停止", style="Panel.TLabel").grid(row=2, column=2, sticky="w", padx=(12, 0), pady=7)

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

        status_panel = ttk.Frame(self.root, style="Panel.TFrame", padding=(16, 10))
        status_panel.pack(fill="x", padx=28, pady=(8, 4))
        ttk.Label(status_panel, text="状态", style="Panel.TLabel").pack(side="left")
        self.status = tk.StringVar(value="等待设备")
        ttk.Label(status_panel, textvariable=self.status, style="Status.TLabel").pack(side="right")

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=28, pady=(8, 24))
        ttk.Label(log_frame, text="运行日志", style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.log = scrolledtext.ScrolledText(log_frame, height=12, bg="#0c1117", fg="#b8c7d3", insertbackground="#f2b84b", relief="flat", borderwidth=0, font=("Cascadia Mono", 9), padx=12, pady=10)
        self.log.pack(fill="both", expand=True)
        self.write_log("控制台已就绪。请解锁设备并点击“检查设备”。")

    def worker_command(self, *args):
        if WORKER.exists():
            return [str(WORKER), *args]
        return [sys.executable, str(BASE_DIR / "worker.py"), *args]

    def write_log(self, text):
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")

    def execute(self, args, action=False):
        target = self.action_process if action else self.process
        if target and target.poll() is None:
            return
        process = subprocess.Popen(self.worker_command(*args), cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        if action:
            self.action_process = process
        else:
            self.process = process
        threading.Thread(target=self.read_process, args=(process,), daemon=True).start()

    def read_process(self, process):
        for line in process.stdout:
            self.output_queue.put((process, line))
        self.output_queue.put((process, f"[进程结束，退出码 {process.wait()}]"))

    def consume_output(self):
        while not self.output_queue.empty():
            process, line = self.output_queue.get_nowait()
            self.write_log(line)
            if process is self.process and process.poll() is not None:
                self.process = None
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.status.set("已停止")
            if process is self.action_process and process.poll() is not None:
                self.action_process = None
                self.check_button.configure(state="normal")
                self.mount_button.configure(state="normal")
                self.status.set("就绪")
        self.root.after(100, self.consume_output)

    def check_device(self):
        self.status.set("检查中")
        self.check_button.configure(state="disabled")
        self.write_log("正在检查设备连接...")
        self.execute(("--check",), action=True)

    def mount_image(self):
        self.status.set("挂载中")
        self.mount_button.configure(state="disabled")
        self.write_log("正在挂载开发者镜像...")
        self.execute(("--mount",), action=True)

    def start_run(self):
        try:
            speed = float(self.speed.get())
            minutes = int(self.duration.get())
            if speed <= 0 or minutes < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("配置错误", "速度必须大于 0，时长必须是非负整数。")
            return
        self.status.set("模拟运行中")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.write_log(f"开始模拟：{self.route.get()} / {speed:g} m/s / {minutes} 分钟")
        self.execute(("--run", "--route", self.route.get(), "--speed", str(speed), "--minutes", str(minutes)))

    def stop_run(self):
        if not self.process or self.process.poll() is not None:
            return
        self.write_log("正在停止模拟...")
        try:
            self.process.send_signal(signal.CTRL_BREAK_EVENT)
        except (AttributeError, OSError):
            self.process.terminate()

    def close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("确认退出", "模拟仍在运行，确定要退出吗？"):
                return
            self.stop_run()
        self.root.destroy()


if __name__ == "__main__":
    app_root = tk.Tk()
    RunnerApp(app_root)
    app_root.mainloop()