migrations = {
    "1.0.0": [
        # Modèle de transaction récurrente : génère de vraies transactions à
        # échéance régulière (ex : frais bancaires mensuels). start_date sert
        # d'ancre ; les échéances = start_date + n périodes. last_run_date =
        # dernière date générée, pour ne pas dupliquer.
        """CREATE TABLE recurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            amount_cents INTEGER NOT NULL,
            from_entity_id INTEGER NOT NULL,
            to_entity_id INTEGER NOT NULL,
            category_id INTEGER,
            contact_id INTEGER,
            frequency TEXT NOT NULL DEFAULT 'monthly',
            start_date TEXT NOT NULL,
            end_date TEXT,
            last_run_date TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )""",
    ],
}
