#!/usr/bin/env python3
"""Mode developpement : backend auto-reload + frontend HMR.

Backend  -> http://localhost:8000  (reload auto sur modif Python)
Frontend -> http://localhost:5173  <- ouvre celui-la
"""
import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"


def main():
    print("=" * 50)
    print("  OpenFlow - mode developpement")
    print("  Backend  : http://localhost:8000")
    print("  Frontend : http://localhost:5173  <- ouvre celui-la")
    print("  Ctrl+C pour tout arreter")
    print("=" * 50)

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:create_app",
         "--factory", "--reload", "--port", "8000", "--host", "127.0.0.1"],
        cwd=str(ROOT),
    )

    frontend = subprocess.Popen(
        "bun run dev",
        cwd=str(FRONTEND),
        shell=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

    try:
        backend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if backend.poll() is None:
            backend.terminate()
        if frontend.poll() is None:
            frontend.terminate()


if __name__ == "__main__":
    main()
