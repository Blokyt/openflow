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
    config_file = PROJECT_ROOT / "config.yaml"
    if not config_file.exists():
        config_example = PROJECT_ROOT / "config.example.yaml"
        if config_example.exists():
            import shutil
            shutil.copy2(str(config_example), str(config_file))
            print("config.yaml cree depuis config.example.yaml")
        else:
            print("ERREUR: config.yaml introuvable. Lancez: python setup.py")
            sys.exit(1)

    sys.path.insert(0, str(PROJECT_ROOT))
    from backend.core.config import load_config
    config = load_config(str(config_file))
    host = config.server.host
    port = config.server.port

    run_migrations()
    check_frontend_build()

    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"

    print(f"\n{'=' * 50}")
    print(f"  OpenFlow")
    print(f"  Local  : http://localhost:{port}")
    if host == "0.0.0.0":
        print(f"  Réseau : http://{local_ip}:{port}")
        print(f"  (écoute LAN : HTTP non chiffré, réservez ce mode au réseau de l'école)")
    else:
        print(f"  (écoute locale uniquement ; passez server.host à 0.0.0.0 dans config.yaml pour le LAN)")
    print(f"{'=' * 50}\n")

    import threading
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    # Un seul worker : SQLite (WAL) n'accepte qu'un processus écrivain.
    uvicorn.run("backend.main:create_app", host=host, port=port, factory=True, reload=False)

if __name__ == "__main__":
    main()
