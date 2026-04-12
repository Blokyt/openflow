migrations = {
    "1.0.0": [
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'reader',
            display_name TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )""",
    ],
    "1.1.0": [
        """CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE user_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'lecteur',
            UNIQUE(user_id, entity_id)
        )""",
    ],
}
