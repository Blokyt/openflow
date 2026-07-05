migrations = {
    "1.0.0": [
        """CREATE TABLE attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            mime_type TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
        )""",
    ],
    "1.1.0": [
        # transaction_id devient nullable et submission_id apparaît : un
        # justificatif est lié soit à une transaction, soit à une soumission
        # (les deux après approbation, pour l'historique).
        """CREATE TABLE attachments_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            submission_id INTEGER,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            mime_type TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """INSERT INTO attachments_v2 (id, transaction_id, submission_id, filename, original_name, mime_type, size, created_at)
           SELECT id, transaction_id, NULL, filename, original_name, mime_type, size, created_at FROM attachments""",
        "DROP TABLE attachments",
        "ALTER TABLE attachments_v2 RENAME TO attachments",
    ],
}
