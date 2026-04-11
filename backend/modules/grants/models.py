migrations = {
    "1.0.0": [
        """CREATE TABLE grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grantor_contact_id INTEGER,
            amount_granted REAL NOT NULL,
            amount_received REAL DEFAULT 0,
            date_granted TEXT NOT NULL,
            date_received TEXT,
            purpose TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (grantor_contact_id) REFERENCES contacts(id)
        )""",
    ],
}
