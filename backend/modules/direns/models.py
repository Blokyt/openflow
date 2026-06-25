"""Modèles de données du module DirENS.

Migration 1.0.0 : table de correspondance catégorie -> ligne du template DirENS.
Le template officiel impose une nomenclature de natures FIXE (Nourriture,
Boissons, Location de salles, Assurance, etc.). Cette table associe chaque
catégorie OpenFlow au numéro de ligne Excel correspondant, ce qui rend l'export
100 % déterministe et réutilisable d'une année sur l'autre.

  - `direns_row`  : numéro de ligne Excel absolu (8 = Nourriture, 15 = Location
                    d'hébergement, 35 = Financement DirENS, ...).
  - `section`     : 'expense' (lignes de dépense 8-32) ou 'income' (lignes de
                    financement 35-37). Une catégorie de recette se mappe en
                    section 'income'.
Une catégorie non mappée n'apparaît tout simplement pas dans le fichier généré.
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
