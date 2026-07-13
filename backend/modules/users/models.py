migrations = {
    "1.0.0": [
        """CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login_at TEXT
        )""",
        """CREATE TABLE sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            user_agent TEXT NOT NULL DEFAULT ''
        )""",
        """CREATE TABLE user_entity_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('treasurer', 'viewer')),
            created_at TEXT NOT NULL,
            UNIQUE(user_id, entity_id)
        )""",
        """CREATE TABLE invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            roles_json TEXT NOT NULL DEFAULT '[]',
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_roles_user ON user_entity_roles(user_id)",
    ],
    "1.1.0": [
        """CREATE TABLE login_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            ip TEXT NOT NULL DEFAULT '',
            success INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            user_agent TEXT NOT NULL DEFAULT ''
        )""",
        "CREATE INDEX IF NOT EXISTS idx_login_events_email ON login_events(email, id)",
        "CREATE INDEX IF NOT EXISTS idx_login_events_ip ON login_events(ip, id)",
    ],
    "1.2.0": [
        """CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets(user_id)",
    ],
}
