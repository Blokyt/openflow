migrations = {
    "1.0.0": [
        """CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_name TEXT DEFAULT '',
            action TEXT NOT NULL,
            table_name TEXT NOT NULL,
            record_id INTEGER,
            old_value TEXT,
            new_value TEXT
        )""",
    ],
}
