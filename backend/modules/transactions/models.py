migrations = {
    "1.0.0": [
        """CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL NOT NULL,
            category_id INTEGER,
            division_id INTEGER,
            contact_id INTEGER,
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    ],
}
