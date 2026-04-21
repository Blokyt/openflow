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
    "1.1.0": [
        "ALTER TABLE budgets ADD COLUMN entity_id INTEGER",
    ],
    "1.2.0": [
        # Legacy `budgets` table is empty in every known install — drop it.
        "DROP TABLE IF EXISTS budgets",
        """CREATE TABLE fiscal_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE fiscal_year_opening_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id)
        )""",
        """CREATE TABLE budget_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            category_id INTEGER,
            amount REAL NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id, category_id)
        )""",
    ],
}
