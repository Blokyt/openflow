migrations = {
    "1.0.0": [
        """CREATE TABLE contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'other',
            email TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    ],
    "1.1.0": [
        # Perf : filtrage/agrégation par type de contact.
        "CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(type)",
    ],
}
