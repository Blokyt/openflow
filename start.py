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
        from shutil import which
        if which("bun") is None:
            print("ERREUR: bun introuvable. Installez-le depuis https://bun.sh")
            print("(le lockfile du projet est bun.lock ; ne pas utiliser npm)")
            sys.exit(1)
        if not (frontend_dir / "node_modules").exists():
            print("Installing frontend dependencies...")
            subprocess.run(["bun", "install"], cwd=str(frontend_dir), check=True)
        subprocess.run(["bun", "run", "build"], cwd=str(frontend_dir), check=True)

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

    # HTTPS local optionnel (certificat auto-signé) : nécessaire pour le retour
    # d'authentification bancaire Enable Banking sans copier/coller.
    ssl_kwargs = {}
    scheme = "http"
    if getattr(config.server, "https", False):
        from backend.core.tls import ensure_dev_cert
        cert_path, key_path = ensure_dev_cert(PROJECT_ROOT / "data" / "tls")
        ssl_kwargs = {"ssl_certfile": str(cert_path), "ssl_keyfile": str(key_path)}
        scheme = "https"

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
    print(f"  Local  : {scheme}://localhost:{port}")
    if scheme == "https":
        print(f"  (HTTPS local : certificat auto-signé, accepte l'avertissement du navigateur une fois)")
    loopback = host in ("127.0.0.1", "localhost", "::1")
    if not loopback:
        print(f"  Réseau : {scheme}://{local_ip}:{port}")
    print(f"{'=' * 50}\n")
    # Avertissement sécurité : écoute réseau (non-loopback) SANS HTTPS => les
    # cookies de session et les mots de passe transitent en clair, interceptables
    # sur le réseau (WiFi partagé...). On le signale fort au démarrage.
    if not loopback and scheme == "http":
        print("  ⚠  SÉCURITÉ : écoute réseau en HTTP non chiffré.")
        print("     Les mots de passe et sessions circulent EN CLAIR sur le réseau.")
        print("     Passez server.https à true dans config.yaml (certificat auto-signé)")
        print("     avant toute mise en production / usage sur un WiFi partagé.\n")

    import threading
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"{scheme}://localhost:{port}")
    threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    # Un seul worker : SQLite (WAL) n'accepte qu'un processus écrivain.
    uvicorn.run("backend.main:create_app", host=host, port=port, factory=True, reload=False, **ssl_kwargs)

if __name__ == "__main__":
    main()
