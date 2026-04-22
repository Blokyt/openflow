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
    "1.1.0": [
        "ALTER TABLE reimbursements ADD COLUMN contact_id INTEGER REFERENCES contacts(id)",
    ],
    "1.2.0": [
        """CREATE TABLE reimbursements_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            person_name TEXT DEFAULT '',
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            reimbursed_date TEXT,
            reimbursement_transaction_id INTEGER,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            contact_id INTEGER REFERENCES contacts(id),
            FOREIGN KEY (transaction_id) REFERENCES transactions(id),
            FOREIGN KEY (reimbursement_transaction_id) REFERENCES transactions(id)
        )""",
        "INSERT INTO reimbursements_new SELECT id, transaction_id, person_name, amount, status, reimbursed_date, reimbursement_transaction_id, notes, created_at, updated_at, contact_id FROM reimbursements",
        "DROP TABLE reimbursements",
        "ALTER TABLE reimbursements_new RENAME TO reimbursements",
    ],
}
