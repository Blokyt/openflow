"""Sauvegarde externe : copie à chaud de la base, justificatifs, rotation."""
import sqlite3
from pathlib import Path

from backend.core.config import load_config
from tools.backup_externe import backup_database, copy_attachments, rotate, run_backup


def _make_source_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY, label TEXT)")
    conn.execute("INSERT INTO transactions (label) VALUES ('Achat gâteaux')")
    conn.commit()
    conn.close()


def test_backup_database_hot_copy(tmp_path):
    src = tmp_path / "openflow.db"
    _make_source_db(src)
    # Connexion ouverte pendant la copie : l'API backup SQLite doit fonctionner à chaud.
    live = sqlite3.connect(str(src))
    try:
        dest = tmp_path / "sortie" / "openflow.db"
        backup_database(src, dest)
    finally:
        live.close()
    copy = sqlite3.connect(str(dest))
    try:
        assert copy.execute("SELECT label FROM transactions").fetchone()[0] == "Achat gâteaux"
    finally:
        copy.close()


def test_copy_attachments(tmp_path):
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "a.pdf").write_bytes(b"%PDF-a")
    (attachments / "b.pdf").write_bytes(b"%PDF-b")
    dest = tmp_path / "dest"
    assert copy_attachments(attachments, dest) == 2
    assert (dest / "a.pdf").read_bytes() == b"%PDF-a"


def test_copy_attachments_missing_dir(tmp_path):
    assert copy_attachments(tmp_path / "inexistant", tmp_path / "dest") == 0


def test_rotate_keeps_most_recent(tmp_path):
    for i in range(5):
        (tmp_path / f"openflow-2026070{i}-000000").mkdir()
    (tmp_path / "autre-dossier").mkdir()  # jamais touché par la rotation
    removed = rotate(tmp_path, retention=3)
    assert sorted(removed) == ["openflow-20260700-000000", "openflow-20260701-000000"]
    assert (tmp_path / "autre-dossier").exists()
    remaining = sorted(d.name for d in tmp_path.iterdir() if d.name.startswith("openflow-"))
    assert len(remaining) == 3


def test_run_backup_full(tmp_path):
    src_db = tmp_path / "openflow.db"
    _make_source_db(src_db)
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "recu.pdf").write_bytes(b"%PDF-recu")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("modules:\n  transactions: true\n", encoding="utf-8")
    destination = tmp_path / "nas"

    target = run_backup(destination, 14, src_db, attachments, config_file)

    assert target.name.startswith("openflow-")
    assert (target / "openflow.db").exists()
    assert (target / "attachments" / "recu.pdf").read_bytes() == b"%PDF-recu"
    assert (target / "config.yaml").exists()


def test_external_backup_config_defaults(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("modules:\n  transactions: true\n", encoding="utf-8")
    config = load_config(str(p))
    assert config.external_backup.destination == ""
    assert config.external_backup.retention == 14


def test_external_backup_config_parsed(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "external_backup:\n  destination: 'Z:/sauvegardes/openflow'\n  retention: 7\n",
        encoding="utf-8",
    )
    config = load_config(str(p))
    assert config.external_backup.destination == "Z:/sauvegardes/openflow"
    assert config.external_backup.retention == 7
