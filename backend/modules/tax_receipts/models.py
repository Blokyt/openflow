migrations = {
    "1.0.0": [
        """CREATE TABLE tax_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            contact_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            fiscal_year TEXT NOT NULL,
            purpose TEXT DEFAULT '',
            generated_at TEXT NOT NULL,
            FOREIGN KEY (contact_id) REFERENCES contacts(id)
        )""",
    ],
}
