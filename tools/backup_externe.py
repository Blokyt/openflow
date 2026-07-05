#!/usr/bin/env python3
"""Sauvegarde quotidienne externe : base SQLite + justificatifs, avec rotation.

Copie vers un dossier de destination (partage réseau, NAS, dossier Drive
monté) configuré dans config.yaml (section external_backup) ou passé en
argument. La base est copiée à chaud via l'API de backup SQLite (fiable même
pendant que le serveur tourne, WAL compris). À planifier une fois par jour
via le Planificateur de tâches Windows : voir docs/deploiement-lan.md.

Usage :
    python tools/backup_externe.py
    python tools/backup_externe.py --destination "Z:/sauvegardes/openflow" --retention 7
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import load_config  # noqa: E402


def backup_database(db_path: Path, dest_file: Path) -> None:
    """Copie à chaud de la base via l'API backup de SQLite (cohérente sous WAL)."""
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest_file))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def copy_attachments(attachments_dir: Path, dest_dir: Path) -> int:
    """Copie tous les justificatifs, renvoie le nombre de fichiers copiés."""
    if not attachments_dir.exists():
        return 0
    dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in attachments_dir.iterdir():
        if f.is_file():
            shutil.copy2(str(f), str(dest_dir / f.name))
            count += 1
    return count


def rotate(destination: Path, retention: int) -> list[str]:
    """Supprime les sauvegardes les plus anciennes au-delà de `retention`.

    Ne touche qu'aux dossiers openflow-* (horodatés, donc triables par nom).
    """
    if retention <= 0:
        return []
    dirs = sorted(
        d for d in destination.iterdir()
        if d.is_dir() and d.name.startswith("openflow-")
    )
    removed = []
    for old in dirs[:-retention]:
        shutil.rmtree(str(old))
        removed.append(old.name)
    return removed


def run_backup(destination: Path, retention: int, db_path: Path,
               attachments_dir: Path, config_file: Path) -> Path:
    """Crée une sauvegarde datée complète puis applique la rotation."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = destination / f"openflow-{stamp}"
    backup_database(db_path, target / "openflow.db")
    count = copy_attachments(attachments_dir, target / "attachments")
    if config_file.exists():
        shutil.copy2(str(config_file), str(target / "config.yaml"))
    removed = rotate(destination, retention)
    print(f"Sauvegarde créée : {target} ({count} justificatif(s))")
    for name in removed:
        print(f"Rotation : {name} supprimée")
    return target


def main():
    parser = argparse.ArgumentParser(
        description="Sauvegarde externe OpenFlow (base + justificatifs + config)")
    parser.add_argument("--destination",
                        help="Dossier de destination (défaut : external_backup.destination de config.yaml)")
    parser.add_argument("--retention", type=int,
                        help="Nombre de sauvegardes conservées (défaut : external_backup.retention)")
    args = parser.parse_args()

    config_file = PROJECT_ROOT / "config.yaml"
    destination, retention = args.destination, args.retention
    if destination is None or retention is None:
        if not config_file.exists():
            print("ERREUR : config.yaml introuvable et aucune --destination fournie.", file=sys.stderr)
            sys.exit(1)
        config = load_config(str(config_file))
        if destination is None:
            destination = config.external_backup.destination
        if retention is None:
            retention = config.external_backup.retention

    if not destination:
        print("ERREUR : aucune destination configurée. Renseignez external_backup.destination "
              "dans config.yaml ou passez --destination.", file=sys.stderr)
        sys.exit(1)

    db_path = PROJECT_ROOT / "data" / "openflow.db"
    if not db_path.exists():
        print(f"ERREUR : base introuvable ({db_path}).", file=sys.stderr)
        sys.exit(1)

    run_backup(Path(destination), retention, db_path,
               PROJECT_ROOT / "data" / "attachments", config_file)


if __name__ == "__main__":
    main()
