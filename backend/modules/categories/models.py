migrations = {
    "1.0.0": [
        """CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            color TEXT DEFAULT '#6B7280',
            icon TEXT DEFAULT 'tag',
            position INTEGER DEFAULT 0,
            FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL
        )""",
    ],
}
