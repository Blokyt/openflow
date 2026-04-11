migrations = {
    "1.0.0": [
        """CREATE TABLE divisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            color TEXT DEFAULT '#6B7280',
            position INTEGER DEFAULT 0
        )""",
    ],
}
