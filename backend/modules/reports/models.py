"""Database models for Rapports module.

Migration 1.1.0 : plan comptable associatif simplifié (règlement ANC 2018-06
allégé) + pont non destructif catégorie -> compte. Le sens produit/charge reste
porté par from_entity_id -> to_entity_id ; le mapping ne sert qu'à VENTILER les
catégories en postes normalisés, jamais à changer les totaux.
  - classe 7 = produits, classe 6 = charges (compte de résultat)
  - classes 1, 4, 5 = postes du bilan (fonds associatifs, créances/dettes, trésorerie)
Une catégorie non mappée tombe dans le compte « Autres » de son sens (is_default=1).
"""

migrations = {
    "1.0.0": [],
    "1.1.0": [
        # Plan comptable simplifié.
        """CREATE TABLE IF NOT EXISTS report_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            label TEXT NOT NULL,
            kind TEXT NOT NULL,            -- 'produit' | 'charge' | 'actif' | 'passif'
            pcg_class INTEGER NOT NULL,    -- 1..7
            is_default INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0
        )""",
        # Pont catégorie -> compte (1 catégorie = au plus 1 compte 6/7).
        """CREATE TABLE IF NOT EXISTS category_account_map (
            category_id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL
        )""",
        # Seed du plan comptable (accents obligatoires — contenu lu par le trésorier).
        """INSERT INTO report_accounts (code, label, kind, pcg_class, is_default, position) VALUES
            ('70',  'Ventes, prestations et recettes d''activités', 'produit', 7, 0, 10),
            ('74',  'Subventions d''exploitation', 'produit', 7, 0, 20),
            ('756', 'Cotisations', 'produit', 7, 0, 30),
            ('754', 'Dons et mécénat', 'produit', 7, 0, 40),
            ('76',  'Produits financiers', 'produit', 7, 0, 50),
            ('77',  'Produits exceptionnels', 'produit', 7, 0, 60),
            ('75',  'Autres produits de gestion courante', 'produit', 7, 1, 70),
            ('60',  'Achats (fournitures, nourriture, petit matériel)', 'charge', 6, 0, 110),
            ('61',  'Services extérieurs (locations, entretien, assurances)', 'charge', 6, 0, 120),
            ('62',  'Autres services extérieurs (prestations, transport, communication, frais bancaires)', 'charge', 6, 0, 130),
            ('63',  'Impôts et taxes', 'charge', 6, 0, 140),
            ('64',  'Charges de personnel', 'charge', 6, 0, 150),
            ('66',  'Charges financières', 'charge', 6, 0, 160),
            ('67',  'Charges exceptionnelles', 'charge', 6, 0, 170),
            ('65',  'Autres charges de gestion courante', 'charge', 6, 1, 180),
            ('512', 'Disponibilités (banque, caisse)', 'actif', 5, 0, 210),
            ('41',  'Créances (produits à recevoir)', 'actif', 4, 0, 220),
            ('40',  'Dettes (charges à payer)', 'passif', 4, 0, 230),
            ('10',  'Fonds associatifs et report à nouveau', 'passif', 1, 0, 240),
            ('12',  'Résultat de l''exercice', 'passif', 1, 0, 250)
        """,
    ],
    "1.2.0": [
        # Couche engagement : régularisations de fin d'exercice (rattachement).
        #   kind='creance' -> produit à recevoir (subvention/cotisation due non encaissée)
        #   kind='dette'   -> charge à payer (facture reçue non payée)
        # Pour éviter le double comptage, les régularisations de l'exercice N-1
        # sont contre-passées (extournées) au calcul de l'exercice N : voir
        # _compte_resultat_for_fy dans api.py. Montants en centimes positifs.
        """CREATE TABLE IF NOT EXISTS report_accruals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year_id INTEGER NOT NULL,
            kind TEXT NOT NULL,            -- 'creance' | 'dette'
            amount INTEGER NOT NULL,       -- centimes, positif
            category_id INTEGER,
            entity_id INTEGER,
            label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_accruals_fy ON report_accruals(fiscal_year_id, kind)",
    ],
}
