migrations = {
    "1.0.0": [
        """CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            division_id INTEGER,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            amount REAL NOT NULL,
            label TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (division_id) REFERENCES divisions(id)
        )""",
    ],
    "1.1.0": [
        "ALTER TABLE budgets ADD COLUMN entity_id INTEGER",
    ],
    "1.2.0": [
        # Legacy `budgets` table is empty in every known install — drop it.
        "DROP TABLE IF EXISTS budgets",
        """CREATE TABLE fiscal_years (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 0,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE fiscal_year_opening_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id)
        )""",
        """CREATE TABLE budget_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            category_id INTEGER,
            amount REAL NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id, category_id)
        )""",
    ],
    "1.3.0": [
        # Recreate fiscal_years: end_date nullable, drop is_current
        """CREATE TABLE fiscal_years_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            start_date TEXT NOT NULL,
            end_date TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """INSERT INTO fiscal_years_v2 (id, name, start_date, end_date, notes, created_at, updated_at)
           SELECT id, name, start_date, end_date, notes, created_at, updated_at FROM fiscal_years""",
        "DROP TABLE fiscal_years",
        "ALTER TABLE fiscal_years_v2 RENAME TO fiscal_years",
    ],
    "1.4.0": [
        # C2 : montants en centimes entiers (on conserve le signe des soldes d'ouverture).
        """CREATE TABLE fiscal_year_opening_balances_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id)
        )""",
        """INSERT INTO fiscal_year_opening_balances_v2 (id, fiscal_year_id, entity_id, amount, source, notes, created_at, updated_at)
           SELECT id, fiscal_year_id, entity_id,
                  CAST(ROUND(amount * 100) AS INTEGER),
                  source, notes, created_at, updated_at
           FROM fiscal_year_opening_balances""",
        "DROP TABLE fiscal_year_opening_balances",
        "ALTER TABLE fiscal_year_opening_balances_v2 RENAME TO fiscal_year_opening_balances",
        """CREATE TABLE budget_allocations_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            category_id INTEGER,
            amount INTEGER NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id, category_id)
        )""",
        """INSERT INTO budget_allocations_v2 (id, fiscal_year_id, entity_id, category_id, amount, notes, created_at, updated_at)
           SELECT id, fiscal_year_id, entity_id, category_id,
                  CAST(ROUND(amount * 100) AS INTEGER),
                  notes, created_at, updated_at
           FROM budget_allocations""",
        "DROP TABLE budget_allocations",
        "ALTER TABLE budget_allocations_v2 RENAME TO budget_allocations",
    ],
    "1.5.0": [
        # Lot C : lien explicite N-1, unicité exercice ouvert, normalisation end_date.
        # Normalise les end_date vides en NULL.
        "UPDATE fiscal_years SET end_date = NULL WHERE end_date = ''",
        # Ajoute le lien explicite vers l'exercice précédent.
        "ALTER TABLE fiscal_years ADD COLUMN previous_fiscal_year_id INTEGER",
        # Index unicité : un seul exercice ouvert (end_date IS NULL) à la fois.
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fy_open ON fiscal_years(end_date) WHERE end_date IS NULL",
    ],
    "1.6.0": [
        # Documentation du bureau sur l'exercice (reprend ce que portait l'ancien module mandates).
        "ALTER TABLE fiscal_years ADD COLUMN president_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE fiscal_years ADD COLUMN tresorier_name TEXT NOT NULL DEFAULT ''",
    ],
    "1.7.0": [
        # Refonte budget dépense/recette : chaque allocation porte une `direction`.
        # La contrainte d'unicité inclut désormais la direction, ce qui permet une
        # ligne dépense ET une ligne recette pour le même (exercice, entité, catégorie).
        # Les allocations existantes (montant unique) deviennent des dépenses : c'est
        # l'heuristique la plus sûre ; le trésorier ressaisit les recettes prévues.
        """CREATE TABLE budget_allocations_v3 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            entity_id INTEGER NOT NULL,
            category_id INTEGER,
            direction TEXT NOT NULL DEFAULT 'expense' CHECK(direction IN ('expense','income')),
            amount INTEGER NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (fiscal_year_id, entity_id, category_id, direction)
        )""",
        """INSERT INTO budget_allocations_v3
               (id, fiscal_year_id, entity_id, category_id, direction, amount, notes, created_at, updated_at)
           SELECT id, fiscal_year_id, entity_id, category_id, 'expense', amount, notes, created_at, updated_at
           FROM budget_allocations""",
        "DROP TABLE budget_allocations",
        "ALTER TABLE budget_allocations_v3 RENAME TO budget_allocations",
        "CREATE INDEX IF NOT EXISTS idx_alloc_direction ON budget_allocations(fiscal_year_id, entity_id, direction)",
    ],
}
