import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
URL = f"http://localhost:{FRONTEND_PORT}"
WIN = os.name == "nt"


def wait_for_port(port, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.5)
    return False


def open_in_chrome(url):
    candidates = [
        os.environ.get("PROGRAMFILES", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome") or "",
        shutil.which("chrome") or "",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            subprocess.Popen([c, url])
            return
    webbrowser.open(url)


def main():
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm not found. Install Node.js first.")
    if not (FRONTEND / "node_modules").exists():
        subprocess.check_call([npm, "install"], cwd=FRONTEND, shell=WIN)

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app:app", "--port", str(BACKEND_PORT)], cwd=ROOT
    )
    frontend = subprocess.Popen([npm, "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"], cwd=FRONTEND, shell=WIN)
    try:
        if wait_for_port(FRONTEND_PORT):
            open_in_chrome(URL)
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (backend, frontend):
            if p.poll() is None:
                if WIN:
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    p.terminate()


if __name__ == "__main__":
    main()
