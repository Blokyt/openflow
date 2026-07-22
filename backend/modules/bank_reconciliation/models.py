migrations = {
    "1.0.0": [
        # Compte bancaire rattaché à une entité interne. Les colonnes eb_* /
        # consent_expires_at ne servent que pour le connecteur Enable Banking
        # (livré en Lot 2) ; en import fichier elles restent vides.
        """CREATE TABLE bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            iban TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'file',
            eb_session_id TEXT NOT NULL DEFAULT '',
            eb_account_id TEXT NOT NULL DEFAULT '',
            consent_expires_at TEXT NOT NULL DEFAULT '',
            last_synced_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT ''
        )""",
        # Une ligne du relevé bancaire. Persistée pour accumuler l'historique
        # au-delà de la fenêtre de 90 jours des API PSD2. amount est SIGNÉ
        # (+ crédit / - débit), en centimes. external_id = FITID (OFX) ou hash
        # stable (CSV) : garantit l'idempotence des ré-imports.
        """CREATE TABLE bank_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_account_id INTEGER NOT NULL,
            external_id TEXT NOT NULL DEFAULT '',
            booking_date TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL DEFAULT 'EUR',
            label TEXT NOT NULL DEFAULT '',
            counterparty TEXT NOT NULL DEFAULT '',
            reconciled_manual INTEGER NOT NULL DEFAULT 0,
            imported_at TEXT NOT NULL,
            UNIQUE (bank_account_id, external_id)
        )""",
        "CREATE INDEX idx_bt_account ON bank_transactions(bank_account_id)",
        # Liaison MANY-TO-MANY (aucune exclusivité) : une ligne bancaire ↔
        # plusieurs écritures (regroupement) ET une écriture ↔ plusieurs lignes
        # bancaires (division). La cohérence est gérée en applicatif (PRAGMA
        # foreign_keys OFF partout dans le projet).
        """CREATE TABLE bank_transaction_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_transaction_id INTEGER NOT NULL,
            transaction_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (bank_transaction_id, transaction_id)
        )""",
        "CREATE INDEX idx_btl_bank ON bank_transaction_links(bank_transaction_id)",
        "CREATE INDEX idx_btl_tx ON bank_transaction_links(transaction_id)",
    ],
    "1.1.0": [
        # Lot 2 : configuration du connecteur Enable Banking (AISP PSD2 gratuit).
        # private_key = clé RSA PEM signant les JWT ; application_id = kid.
        """CREATE TABLE bank_reconciliation_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            application_id TEXT NOT NULL DEFAULT '',
            private_key TEXT NOT NULL DEFAULT '',
            redirect_url TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )""",
    ],
    "1.2.0": [
        # Assistant de configuration intégré : OpenFlow génère lui-même la paire
        # clé/certificat. On conserve le certificat public pour pouvoir le
        # réafficher (à recopier dans Enable Banking lors de l'enregistrement).
        "ALTER TABLE bank_reconciliation_config ADD COLUMN public_cert TEXT NOT NULL DEFAULT ''",
    ],
}
