migrations = {
    "1.0.0": [
        """CREATE TABLE reimbursements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            person_name TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            reimbursed_date TEXT,
            reimbursement_transaction_id INTEGER,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id),
            FOREIGN KEY (reimbursement_transaction_id) REFERENCES transactions(id)
        )""",
    ],
}
