#!/usr/bin/env python3
"""Launch OpenFlow."""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

def check_frontend_build():
    build_dir = PROJECT_ROOT / "frontend" / "dist"
    if not build_dir.exists():
        print("Frontend not built. Building...")
        frontend_dir = PROJECT_ROOT / "frontend"
        if not (frontend_dir / "node_modules").exists():
            print("Installing frontend dependencies...")
            subprocess.run(["npm", "install"], cwd=str(frontend_dir), check=True)
        subprocess.run(["npm", "run", "build"], cwd=str(frontend_dir), check=True)

def run_migrations():
    print("Running migrations...")
    result = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "migrate.py")], capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Migration warnings: {result.stderr}")

def main():
    port = 8000
    host = "127.0.0.1"
    run_migrations()
    check_frontend_build()

    print(f"\n{'=' * 50}")
    print(f"  OpenFlow")
    print(f"  http://{host}:{port}")
    print(f"{'=' * 50}\n")

    import threading
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run("backend.main:create_app", host=host, port=port, factory=True, reload=False)

if __name__ == "__main__":
    main()
