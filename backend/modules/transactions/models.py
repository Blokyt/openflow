migrations = {
    "1.0.0": [
        """CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL NOT NULL,
            category_id INTEGER,
            contact_id INTEGER,
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    ],
    "1.1.0": [
        "ALTER TABLE transactions ADD COLUMN from_entity_id INTEGER",
        "ALTER TABLE transactions ADD COLUMN to_entity_id INTEGER",
    ],
    "1.3.0": [
        # Lot F (performance) : index pour accélérer les jointures budget N+1.
        "CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(date)",
        "CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_tx_to ON transactions(to_entity_id)",
        "CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id)",
    ],
    "1.4.0": [
        # Rapprochement bancaire : colonnes reconciled et reconciled_at.
        # Ces ALTER échouent si la colonne existe déjà — migrate.py skippe "already exists".
        "ALTER TABLE transactions ADD COLUMN reconciled INTEGER DEFAULT 0",
        "ALTER TABLE transactions ADD COLUMN reconciled_at TEXT",
    ],
    "1.2.0": [
        # C1 + C2 : montant en centimes entiers, TOUJOURS positif (ABS).
        # Le sens d'une transaction vient desormais uniquement de from/to.
        """CREATE TABLE transactions_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount INTEGER NOT NULL,
            category_id INTEGER,
            contact_id INTEGER,
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            from_entity_id INTEGER,
            to_entity_id INTEGER
        )""",
        """INSERT INTO transactions_v2 (id, date, label, description, amount, category_id, contact_id, created_by, created_at, updated_at, from_entity_id, to_entity_id)
           SELECT id, date, label, description,
                  CAST(ROUND(ABS(amount) * 100) AS INTEGER),
                  category_id, contact_id, created_by, created_at, updated_at,
                  from_entity_id, to_entity_id
           FROM transactions""",
        "DROP TABLE transactions",
        "ALTER TABLE transactions_v2 RENAME TO transactions",
    ],
}
