migrations = {
    "1.0.0": [
        # Une poche = un emplacement physique de l'argent (compte, livret,
        # caisse). balance = reference_cents + solde net des transferts.
        # reference_cents / reference_date : solde fixé à un instant t (même
        # principe que entity_balance_refs). bank_account_id : lien optionnel
        # vers un compte du module bank_reconciliation pour comparer au réel.
        """CREATE TABLE pockets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            reference_cents INTEGER NOT NULL DEFAULT 0,
            reference_date TEXT NOT NULL DEFAULT '',
            bank_account_id INTEGER,
            created_at TEXT NOT NULL DEFAULT ''
        )""",
        # Transfert d'une poche à une autre : ne change pas le total, ne touche
        # pas la compta des clubs (c'est un pur déplacement de trésorerie).
        """CREATE TABLE pocket_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_pocket_id INTEGER NOT NULL,
            to_pocket_id INTEGER NOT NULL,
            amount_cents INTEGER NOT NULL,
            date TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX idx_ptr_from ON pocket_transfers(from_pocket_id)",
        "CREATE INDEX idx_ptr_to ON pocket_transfers(to_pocket_id)",
        # Trois poches par défaut ; l'utilisateur peut les renommer / en ajouter.
        "INSERT INTO pockets (name, position, reference_cents, reference_date, created_at) VALUES ('Compte', 0, 0, '', '')",
        "INSERT INTO pockets (name, position, reference_cents, reference_date, created_at) VALUES ('Livret', 1, 0, '', '')",
        "INSERT INTO pockets (name, position, reference_cents, reference_date, created_at) VALUES ('Caisse', 2, 0, '', '')",
    ],
}
