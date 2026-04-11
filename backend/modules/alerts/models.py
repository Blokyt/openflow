migrations = {
    "1.0.0": [
        """CREATE TABLE alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            label TEXT NOT NULL,
            threshold REAL,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )""",
    ],
}
