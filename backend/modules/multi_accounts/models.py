migrations = {
    "1.0.0": [
        """CREATE TABLE accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'checking',
            description TEXT DEFAULT '',
            initial_balance REAL DEFAULT 0,
            color TEXT DEFAULT '#6B7280',
            position INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_account_id INTEGER NOT NULL,
            to_account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            label TEXT DEFAULT '',
            from_transaction_id INTEGER,
            to_transaction_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (from_account_id) REFERENCES accounts(id),
            FOREIGN KEY (to_account_id) REFERENCES accounts(id),
            FOREIGN KEY (from_transaction_id) REFERENCES transactions(id),
            FOREIGN KEY (to_transaction_id) REFERENCES transactions(id)
        )""",
    ],
}
