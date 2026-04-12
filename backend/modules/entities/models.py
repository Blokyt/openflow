migrations = {
    "1.0.0": [
        """CREATE TABLE entities (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            description  TEXT    DEFAULT '',
            type         TEXT    NOT NULL DEFAULT 'internal',
            parent_id    INTEGER,
            is_default   INTEGER NOT NULL DEFAULT 0,
            is_divers    INTEGER NOT NULL DEFAULT 0,
            color        TEXT    DEFAULT '#6B7280',
            position     INTEGER DEFAULT 0,
            created_at   TEXT    NOT NULL,
            updated_at   TEXT    NOT NULL
        )""",
        """CREATE TABLE entity_balance_refs (
            entity_id        INTEGER PRIMARY KEY,
            reference_date   TEXT    NOT NULL,
            reference_amount REAL    NOT NULL DEFAULT 0.0,
            updated_at       TEXT    NOT NULL
        )""",
    ],
}
