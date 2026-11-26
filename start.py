#!/usr/bin/env python3
"""
Cross-platform launcher for Skills2Job (Windows 10/11 and macOS/Linux).
Starts both the FastAPI backend (127.0.0.1:8000) and Next.js frontend (localhost:3000).
"""
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"


def find_backend_python() -> str:
    is_windows = platform.system() == "Windows"
    venv_python = (
        BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
        if is_windows
        else BACKEND_DIR / ".venv" / "bin" / "python"
    )
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def find_npm() -> str:
    candidates = ["npm.cmd", "npm"] if platform.system() == "Windows" else ["npm"]
    for name in candidates:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise FileNotFoundError("npm was not found on PATH. Please install Node.js 18+.")


def main() -> int:
    python_bin = find_backend_python()
    npm_bin = find_npm()

    print("===================================================")
    print(f"Starting Skills2Job ({platform.system()} / {platform.machine()})")
    print(f"Backend Python: {python_bin}")
    print("===================================================")

    backend_proc = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=str(BACKEND_DIR),
    )
    frontend_proc = subprocess.Popen(
        [npm_bin, "run", "dev"],
        cwd=str(FRONTEND_DIR),
    )

    print("Web App:  http://localhost:3000")
    print("API Docs: http://127.0.0.1:8000/docs")
    print("Press Ctrl+C to stop both servers.")

    def shutdown(*_args):
        for proc in (frontend_proc, backend_proc):
            if proc.poll() is None:
                proc.terminate()
        for proc in (frontend_proc, backend_proc):
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            if backend_proc.poll() is not None or frontend_proc.poll() is not None:
                break
            backend_proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
