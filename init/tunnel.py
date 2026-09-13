import logging
import multiprocessing
import re
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RSD_PATTERN = re.compile(r"(?:--rsd\s+)?(\S+)\s+(\d+)$")


def start_tunnel(queue):
    logging.info("tunnel worker starting")
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--tunnel"]
    else:
        command = [sys.executable, "-m", "pymobiledevice3", "lockdown", "start-tunnel", "--script-mode"]
    logging.info("tunnel command: %s", " ".join(command))

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    logging.info("Tunnel started")

    address, port = None, None

    while True:
        output = process.stdout.readline().strip()
        if not output and process.poll() is not None:
            logging.error(f"Tunnel process exited with code {process.returncode}")
            queue.put(None)
            return
        if output:
            logging.info(output)

        match = RSD_PATTERN.search(output)
        if match:
            address, port = match.group(1), int(match.group(2))
            queue.put((address, port))
            logging.info(f"RSD Address: {address}, RSD Port: {port}")
            break

    process.wait()


def terminate_tunnel(process) -> None:
    """Kill the tunnel worker and the process tree it spawned."""
    if process is None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            process.terminate()
    except Exception:
        process.terminate()
    process.join(timeout=3)
    if process.is_alive():
        process.kill()
        process.join(timeout=3)


def tunnel():
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=start_tunnel, args=(queue,))
    process.start()
    
    try:
        result = queue.get(timeout=40)
        if result is None:
            raise RuntimeError("❌ 无法建立隧道连接")
        address, port = result
        
        return process, address, port
    except Exception as e:
        logging.error(
            f"隧道建立失败: {e}。child_alive={process.is_alive()} exitcode={process.exitcode}。"
            "请确认管理员权限、iTunes 驱动和设备开发者模式。"
        )
        terminate_tunnel(process)

    return None, None, None
