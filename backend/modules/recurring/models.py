migrations = {
    "1.0.0": [
        """CREATE TABLE recurring_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount REAL NOT NULL,
            category_id INTEGER,
            division_id INTEGER,
            contact_id INTEGER,
            frequency TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT,
            last_generated TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )""",
    ],
}
