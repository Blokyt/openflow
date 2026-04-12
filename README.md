# OpenFlow

Outil de gestion de tresorerie modulaire. Deployez votre comptabilite depuis un CSV/Excel borderline vers une app locale avec des modules ultra-personnalisables.

## Quickstart

```bash
# Cloner le repo
git clone https://github.com/<user>/openflow.git
cd openflow

# Installer (Python 3.10+, Node.js 18+)
python setup.py

# Lancer
python start.py
# → http://127.0.0.1:8000
```

## Modules disponibles

| Module | Categorie | Description |
|--------|-----------|-------------|
| transactions | noyau | CRUD, filtres, solde dynamique |
| categories | noyau | Hierarchie parent/enfant |
| dashboard | noyau | Cartes de synthese, widgets |
| invoices | standard | Factures & devis |
| reimbursements | standard | Suivi des avances |
| budget | standard | Enveloppes budgetaires |
| divisions | standard | Poles/services/projets |
| tiers | standard | Contacts client/fournisseur |
| attachments | standard | Pieces jointes |
| annotations | standard | Notes sur transactions |
| export | standard | CSV/JSON/bilan |
| bank_reconciliation | avance | Import releves, matching |
| recurring | avance | Transactions recurrentes |
| multi_accounts | avance | Plusieurs comptes |
| audit | avance | Journal des modifications |
| forecasting | avance | Projection cash-flow |
| alerts | avance | Seuils et echeances |
| tax_receipts | avance | Recus fiscaux cerfa |
| grants | avance | Suivi subventions |
| fec_export | avance | Export FEC legal |
| multi_users | avance | Roles admin/tresorier/lecteur |

Activez/desactivez les modules dans `config.yaml` section `modules`, puis relancez l'app.

## Configuration

A la premiere installation, `setup.py` cree `config.yaml` depuis `config.example.yaml`. Editez-le pour configurer votre entite :

```yaml
entity:
  name: Mon Association
  type: association  # association, entreprise, auto-entrepreneur
  currency: EUR
balance:
  amount: 3200.0     # Solde de reference
  date: '2025-06-01' # A cette date
```

## Skill Claude Code

OpenFlow inclut un skill pour [Claude Code](https://claude.ai/claude-code) qui vous guide dans la configuration, l'import de donnees et l'evolution de votre tresorerie.

Pour l'installer :
1. Copiez `skill/SKILL.md` vers `~/.claude/skills/openflow/SKILL.md`
2. Dans Claude Code, le skill se declenche automatiquement quand vous parlez de tresorerie

## Dev

```bash
# Tests
pip install -r requirements-dev.txt
python -m pytest tests/ -v

# Verifier l'integrite du projet
python tools/check.py

# Creer un module custom
python tools/create_module.py mon_module --name "Mon Module" --description "Description"
```

## License

MIT
