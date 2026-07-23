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
    "1.1.0": [
        """ALTER TABLE entities ADD COLUMN balance_mode TEXT NOT NULL DEFAULT 'own' CHECK(balance_mode IN ('own', 'aggregate'))""",
    ],
    "1.2.0": [
        # C2 : reference_amount en centimes entiers. On conserve le SIGNE
        # (un solde de reference peut etre negatif : decouvert bancaire).
        """CREATE TABLE entity_balance_refs_v2 (
            entity_id        INTEGER PRIMARY KEY,
            reference_date   TEXT    NOT NULL,
            reference_amount INTEGER NOT NULL DEFAULT 0,
            updated_at       TEXT    NOT NULL
        )""",
        """INSERT INTO entity_balance_refs_v2 (entity_id, reference_date, reference_amount, updated_at)
           SELECT entity_id, reference_date,
                  CAST(ROUND(reference_amount * 100) AS INTEGER),
                  updated_at
           FROM entity_balance_refs""",
        "DROP TABLE entity_balance_refs",
        "ALTER TABLE entity_balance_refs_v2 RENAME TO entity_balance_refs",
    ],
    "1.3.0": [
        # Feuille "résiduelle" (ex : BDA local) sous une racine agrégée : son
        # solde n'est pas saisi mais DÉDUIT = total Trésorerie − Σ des soldes de
        # ses entités sœurs (les clubs). Un seul résiduel par racine attendu.
        "ALTER TABLE entities ADD COLUMN is_residual INTEGER NOT NULL DEFAULT 0",
    ],
}
