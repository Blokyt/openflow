#!/usr/bin/env python3
"""Setup OpenFlow — installe les dependances et prepare le projet."""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def main():
    print("=" * 50)
    print("  OpenFlow - Installation")
    print("=" * 50)

    # 0. Config
    print("\n[0/4] Verification de la configuration...")
    config_file = PROJECT_ROOT / "config.yaml"
    config_example = PROJECT_ROOT / "config.example.yaml"
    if not config_file.exists():
        if config_example.exists():
            import shutil
            shutil.copy2(str(config_example), str(config_file))
            print("  config.yaml cree depuis config.example.yaml")
        else:
            print("  ERREUR: config.example.yaml introuvable")
            sys.exit(1)
    else:
        print("  config.yaml deja present")

    # 1. Python dependencies
    print("\n[1/4] Installation des dependances Python...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(PROJECT_ROOT / "requirements.txt"), "-q"],
        check=True,
    )
    print("  OK")

    # 2. Frontend dependencies
    print("\n[2/4] Installation des dependances frontend...")
    frontend_dir = PROJECT_ROOT / "frontend"
    subprocess.run(["npm", "install"], cwd=str(frontend_dir), check=True, capture_output=True)
    print("  OK")

    # 3. Build frontend
    print("\n[3/4] Build du frontend...")
    subprocess.run(["npm", "run", "build"], cwd=str(frontend_dir), check=True, capture_output=True)
    print("  OK")

    # 4. Initialize database
    print("\n[4/4] Initialisation de la base de donnees...")
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "migrate.py")],
        check=True, capture_output=True,
    )
    print("  OK")

    # Verify
    print("\n" + "=" * 50)
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "check.py")],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("  Installation terminee avec succes !")
        print(f"\n  Lancer l'app : python start.py")
        print(f"  Ouvrir       : http://127.0.0.1:8000")
    else:
        print("  Attention : verification echouee")
        print(result.stdout)
    print("=" * 50)


if __name__ == "__main__":
    main()
