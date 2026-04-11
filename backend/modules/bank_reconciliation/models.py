migrations = {
    "1.0.0": [
        """CREATE TABLE bank_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            amount REAL NOT NULL,
            matched_transaction_id INTEGER,
            status TEXT DEFAULT 'unmatched',
            imported_at TEXT NOT NULL,
            FOREIGN KEY (matched_transaction_id) REFERENCES transactions(id)
        )""",
    ],
}
