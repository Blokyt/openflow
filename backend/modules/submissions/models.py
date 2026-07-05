migrations = {
    "1.0.0": [
        """CREATE TABLE transaction_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount INTEGER NOT NULL,
            category_id INTEGER,
            entity_id INTEGER NOT NULL,
            counterparty_entity_id INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('expense','income')),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','rejected','cancelled')),
            submitted_by INTEGER NOT NULL,
            reviewed_by INTEGER,
            reviewed_at TEXT,
            review_comment TEXT DEFAULT '',
            transaction_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX idx_submissions_status ON transaction_submissions(status)",
        "CREATE INDEX idx_submissions_submitted_by ON transaction_submissions(submitted_by)",
    ],
}
