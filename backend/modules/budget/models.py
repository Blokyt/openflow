migrations = {
    "1.0.0": [
        """CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            division_id INTEGER,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            amount REAL NOT NULL,
            label TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (division_id) REFERENCES divisions(id)
        )""",
    ],
}
