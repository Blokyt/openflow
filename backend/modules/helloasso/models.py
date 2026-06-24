migrations = {
    "1.0.0": [
        """CREATE TABLE helloasso_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            client_id TEXT NOT NULL DEFAULT '',
            client_secret TEXT NOT NULL DEFAULT '',
            organization_slug TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )""",
        """CREATE TABLE helloasso_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            form_type TEXT NOT NULL,
            form_slug TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT '',
            collected_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'EUR',
            last_synced_at TEXT NOT NULL DEFAULT '',
            UNIQUE (fiscal_year_id, form_type, form_slug)
        )""",
        """CREATE TABLE helloasso_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            form_type TEXT NOT NULL,
            form_slug TEXT NOT NULL,
            category_id INTEGER,
            from_entity_id INTEGER NOT NULL,
            to_entity_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (form_type, form_slug)
        )""",
    ],
    "1.1.0": [
        # Modèle « acquittement » : on pointe le montant pris en compte par campagne.
        # Plus de rattachement catégorie/club ni de calcul d'écart depuis la compta.
        "ALTER TABLE helloasso_campaigns ADD COLUMN acknowledged_cents INTEGER NOT NULL DEFAULT 0",
        "DROP TABLE IF EXISTS helloasso_links",
    ],
    "1.2.0": [
        # Modèle « liaison transactions » : on associe les transactions réelles de la
        # compta à une campagne. linked_cents = somme des transactions liées,
        # pending_cents = collecté - lié. acknowledged_cents devient inerte (le
        # pointage forfaitaire est remplacé par les associations). Une transaction
        # ne peut être liée qu'à une seule campagne (exclusivité applicative).
        """CREATE TABLE helloasso_campaign_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            transaction_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (campaign_id, transaction_id)
        )""",
        "CREATE INDEX idx_hact_tx ON helloasso_campaign_transactions(transaction_id)",
    ],
}
