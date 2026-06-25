"""Modèles de données du module DirENS.

Migration 1.0.0 : table `direns_line_map` historique. Elle servait à un mapping
manuel catégorie -> ligne du template. Ce mapping a été abandonné : l'export
utilise désormais DIRECTEMENT les catégories de l'app comme lignes (aucune
configuration). La table est conservée (création idempotente) pour ne pas casser
les bases déjà migrées, mais elle n'est plus lue ni écrite.
"""

migrations = {
    "1.0.0": [
        """CREATE TABLE IF NOT EXISTS direns_line_map (
            category_id INTEGER PRIMARY KEY,
            direns_row INTEGER NOT NULL,
            section TEXT NOT NULL DEFAULT 'expense',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_direns_line_map_row ON direns_line_map(direns_row)",
    ]
}
