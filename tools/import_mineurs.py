"""Import et nettoyage des contacts depuis mineurs.json.

Usage:
    python tools/import_mineurs.py            # aperçu + confirmation interactive
    python tools/import_mineurs.py --apply    # applique sans confirmation
    python tools/import_mineurs.py --dry-run  # aperçu seul, aucune écriture

Logique :
  - Pour chaque mineur, cherche le meilleur match flou dans les contacts existants
  - Si score >= 90 %  → met à jour le contact existant (unifie les données)
  - Si score 75-89 %  → affiche et demande confirmation au cas par cas
  - Si score < 75 %   → crée un nouveau contact
  - Signale aussi les doublons internes à la base (contacts sans lien avec les mineurs)
"""
import argparse
import difflib
import json
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MINEURS_PATH = PROJECT_ROOT.parent / "mineurs.json"
DB_PATH = PROJECT_ROOT / "data" / "openflow.db"

# Seuils de confiance
THRESHOLD_AUTO   = 0.90   # fusion automatique
THRESHOLD_MANUAL = 0.75   # demande confirmation


# ─── Normalisation ────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    """Minuscules + sans accents + espaces normalisés."""
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # tirets et apostrophes → espace
    s = s.replace("-", " ").replace("'", " ").replace("'", " ")
    return " ".join(s.split())


def _tokens(s: str) -> set[str]:
    return set(_normalize(s).split())


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    seq = difflib.SequenceMatcher(None, na, nb).ratio()

    tokens_a = na.split()
    tokens_b = nb.split()

    if len(tokens_a) >= 2 and len(tokens_b) >= 2:
        first_ratio = difflib.SequenceMatcher(None, tokens_a[0], tokens_b[0]).ratio()
        last_a = " ".join(tokens_a[1:])
        last_b = " ".join(tokens_b[1:])
        last_ratio = difflib.SequenceMatcher(None, last_a, last_b).ratio()
        # Prénom ou nom trop différent → personnes distinctes
        if first_ratio < 0.65 or last_ratio < 0.65:
            return seq * 0.50
        return (seq + first_ratio + last_ratio) / 3

    # Un seul token d'un côté : on ne peut pas vérifier le nom de famille → pénalité
    if len(tokens_a) != len(tokens_b):
        return seq * 0.70

    return seq


def _best_match(name: str, contacts: list[dict]) -> tuple[dict | None, float]:
    best, best_score = None, 0.0
    for c in contacts:
        score = _similarity(name, c["name"])
        if score > best_score:
            best_score = score
            best = c
    return best, best_score


# ─── Chargement ───────────────────────────────────────────────────────────────

def load_mineurs() -> list[dict]:
    with open(MINEURS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    mineurs = []
    for promo_data in data.values():
        for s in promo_data.get("etudiants", []):
            prenom = (s.get("prenom") or "").strip()
            nom    = (s.get("nom") or "").strip()
            name   = f"{prenom} {nom}".strip()
            if not name or name.lower() == "inconnu":
                continue
            mineurs.append({
                "name":  name,
                "email": (s.get("email") or "").strip(),
                "phone": (s.get("telephone") or "").strip(),
                "promo": str(s.get("promo") or "").strip(),
            })
    return mineurs


def load_contacts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM contacts").fetchall()
    return [dict(r) for r in rows]


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply",   action="store_true", help="Applique sans confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Aperçu seul, aucune écriture")
    args = parser.parse_args()

    for path, label in [(MINEURS_PATH, "mineurs.json"), (DB_PATH, "openflow.db")]:
        if not path.exists():
            print(f"[ERREUR] {label} introuvable : {path}")
            sys.exit(1)

    mineurs   = load_mineurs()
    conn      = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    contacts  = load_contacts(conn)

    now = datetime.now(timezone.utc).isoformat()

    # ── Planification ──────────────────────────────────────────────────────────
    to_create: list[dict]               = []   # nouveaux contacts
    to_update: list[tuple[dict, dict]]  = []   # (contact_db, mineur)
    to_confirm: list[tuple[dict, dict, float]] = []  # à confirmer manuellement

    matched_contact_ids: set[int] = set()

    for m in mineurs:
        match, score = _best_match(m["name"], contacts)
        if match and score >= THRESHOLD_AUTO:
            to_update.append((match, m))
            matched_contact_ids.add(match["id"])
        elif match and score >= THRESHOLD_MANUAL:
            to_confirm.append((match, m, score))
            matched_contact_ids.add(match["id"])
        else:
            to_create.append(m)

    # ── Doublons internes (contacts non liés aux mineurs, très similaires entre eux) ──
    unmatched_contacts = [c for c in contacts if c["id"] not in matched_contact_ids]
    internal_dupes: list[tuple[dict, dict, float]] = []
    seen_pairs: set[frozenset] = set()
    for i, ca in enumerate(unmatched_contacts):
        for cb in unmatched_contacts[i+1:]:
            pair = frozenset([ca["id"], cb["id"]])
            if pair in seen_pairs:
                continue
            score = _similarity(ca["name"], cb["name"])
            if score >= THRESHOLD_MANUAL:
                internal_dupes.append((ca, cb, score))
                seen_pairs.add(pair)

    # ── Affichage du plan ──────────────────────────────────────────────────────
    sep = "-" * 60
    print(f"\n{sep}")
    print(f"  mineurs.json   : {len(mineurs)} etudiants")
    print(f"  Contacts en DB : {len(contacts)}")
    print(f"{sep}")
    print(f"  [OK] Fusion auto  (>={int(THRESHOLD_AUTO*100)}%) : {len(to_update)}")
    print(f"  [?]  A confirmer  ({int(THRESHOLD_MANUAL*100)}-{int(THRESHOLD_AUTO*100)-1}%) : {len(to_confirm)}")
    print(f"  [+]  Nouveaux              : {len(to_create)}")
    print(f"  [~]  Doublons internes     : {len(internal_dupes)}")
    print(f"{sep}\n")

    if to_update:
        print("-- Fusions automatiques " + "-" * 36)
        for db_c, m in to_update[:20]:
            score = _similarity(db_c["name"], m["name"])
            print(f"  {db_c['name']!r:35s} <- {m['name']!r}  ({score:.0%})")
        if len(to_update) > 20:
            print(f"  ... et {len(to_update)-20} autres")
        print()

    if to_confirm:
        print("-- Correspondances a confirmer " + "-" * 29)
        for db_c, m, score in to_confirm:
            print(f"  {db_c['name']!r:35s} <- {m['name']!r}  ({score:.0%})")
        print()

    if internal_dupes:
        print("-- Doublons internes detectes " + "-" * 30)
        for ca, cb, score in internal_dupes[:15]:
            print(f"  {ca['name']!r:35s} ~= {cb['name']!r}  ({score:.0%})")
        if len(internal_dupes) > 15:
            print(f"  ... et {len(internal_dupes)-15} autres")
        print()

    if args.dry_run:
        print("[DRY-RUN] Aucune écriture effectuée.")
        conn.close()
        return

    # ── Confirmation interactive pour les cas ambigus ─────────────────────────
    confirmed_updates: list[tuple[dict, dict]] = list(to_update)

    if to_confirm and not args.apply:
        print("-- Confirmation manuelle " + "-" * 35)
        for db_c, m, score in to_confirm:
            ans = input(f"  Fusionner {db_c['name']!r} -> {m['name']!r} ({score:.0%}) ? [o/n] ").strip().lower()
            if ans in ("o", "oui", "y", "yes"):
                confirmed_updates.append((db_c, m))
            else:
                to_create.append(m)
        print()

    if not args.apply and not to_confirm:
        if to_update or to_create:
            ans = input(f"Appliquer ({len(to_update)} mises à jour + {len(to_create)} créations) ? [o/n] ").strip().lower()
            if ans not in ("o", "oui", "y", "yes"):
                print("Annulé.")
                conn.close()
                return

    # ── Application ───────────────────────────────────────────────────────────
    updated = 0
    created = 0

    for db_c, m in confirmed_updates:
        fields: dict = {}
        # Enrichit seulement les champs vides ou le type
        if not db_c.get("email") and m["email"]:
            fields["email"] = m["email"]
        if not db_c.get("phone") and m["phone"]:
            fields["phone"] = m["phone"]
        if db_c.get("type") != "membre":
            fields["type"] = "membre"
        # Corrige le nom vers celui du JSON (source de vérité)
        if _normalize(db_c["name"]) != _normalize(m["name"]):
            fields["name"] = m["name"]
        # Ajoute la promo dans les notes si absente
        promo_note = f"Promo {m['promo']}" if m["promo"] else ""
        if promo_note and promo_note not in (db_c.get("notes") or ""):
            existing_notes = (db_c.get("notes") or "").strip()
            fields["notes"] = f"{existing_notes}\n{promo_note}".strip() if existing_notes else promo_note

        if fields:
            fields["updated_at"] = now
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE contacts SET {set_clause} WHERE id = ?",
                [*fields.values(), db_c["id"]],
            )
            updated += 1

    for m in to_create:
        conn.execute(
            """INSERT INTO contacts (name, type, email, phone, address, notes, created_at, updated_at)
               VALUES (?, 'membre', ?, ?, '', ?, ?, ?)""",
            (m["name"], m["email"], m["phone"],
             f"Promo {m['promo']}" if m["promo"] else "", now, now),
        )
        created += 1

    conn.commit()
    conn.close()

    print(f"[OK] {updated} contacts mis à jour, {created} créés.")
    if internal_dupes:
        print(f"[INFO] {len(internal_dupes)} doublons internes détectés — à traiter manuellement via la page Contacts.")


if __name__ == "__main__":
    main()
