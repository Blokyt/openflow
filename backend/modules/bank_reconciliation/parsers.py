"""Parseurs de relevés bancaires : OFX et CSV (format Caisse d'Épargne / SEPA).

Chaque parseur renvoie une liste de dicts normalisés :
    {external_id, booking_date (YYYY-MM-DD), amount (centimes SIGNÉS),
     currency, label, counterparty}

Le montant est signé : positif = crédit (entrée), négatif = débit (sortie).
external_id assure l'idempotence des ré-imports : FITID natif pour l'OFX, hash
stable (date + libellé + montant + n° d'occurrence) pour le CSV qui n'a pas
toujours d'identifiant de ligne.
"""
import csv
import hashlib
import re
from datetime import datetime


class ParseError(Exception):
    """Fichier illisible ou format non reconnu."""


# ---------------------------------------------------------------------------
# Helpers communs
# ---------------------------------------------------------------------------

def _decode(content: bytes) -> str:
    """Décode en essayant UTF-8 puis Latin-1 (les exports bancaires FR sont
    souvent en Windows-1252/Latin-1)."""
    if isinstance(content, str):
        return content
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace")


def _amount_to_cents(raw: str) -> int:
    """Convertit un montant texte en centimes entiers signés.

    Gère les formats FR (« 1 234,56 », « -1 234,56 ») et EN (« 1234.56 »,
    « -1,234.56 »). Renvoie 0 pour une chaîne vide.
    """
    s = (raw or "").strip()
    if not s:
        return 0
    neg = False
    # Parenthèses comptables : (12,34) = négatif.
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = s.replace(" ", "").replace(" ", "")
    s = s.replace("€", "").replace("EUR", "")
    if s.startswith("+"):
        s = s[1:]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    if not s:
        return 0
    # Détermine le séparateur décimal : le dernier de , ou . rencontré.
    last_comma = s.rfind(",")
    last_dot = s.rfind(".")
    dec_pos = max(last_comma, last_dot)
    if dec_pos == -1:
        int_part, frac_part = s, ""
    else:
        int_part = s[:dec_pos]
        frac_part = s[dec_pos + 1:]
        # Les autres séparateurs sont des milliers → on les retire.
        int_part = int_part.replace(",", "").replace(".", "")
    if not re.fullmatch(r"\d*", int_part) or not re.fullmatch(r"\d*", frac_part):
        raise ParseError(f"Montant illisible : {raw!r}")
    frac_part = (frac_part + "00")[:2]
    cents = int(int_part or "0") * 100 + int(frac_part or "0")
    return -cents if neg else cents


def _norm_date(raw: str) -> str:
    """Normalise une date en YYYY-MM-DD. Accepte JJ/MM/AAAA, AAAA-MM-JJ,
    AAAAMMJJ (OFX). Lève ParseError si non reconnue."""
    s = (raw or "").strip()
    if not s:
        raise ParseError("Date vide")
    # OFX : AAAAMMJJ éventuellement suivi de l'heure et d'un fuseau.
    m = re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    if m and "/" not in s and "-" not in s[:8]:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ParseError(f"Date illisible : {raw!r}")


def _stable_external_id(date: str, label: str, amount: int, occurrence: int) -> str:
    """Identifiant déterministe pour une ligne CSV sans id natif.

    occurrence distingue deux lignes réellement identiques (même date, libellé
    et montant) apparaissant dans le même relevé, sans casser l'idempotence :
    un ré-import du même fichier reproduit exactement les mêmes ids.
    """
    key = f"{date}|{label.strip().lower()}|{amount}|{occurrence}"
    return "csv:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def _assign_external_ids(rows: list) -> list:
    """Complète external_id (hash stable) pour les lignes qui n'en ont pas,
    en comptant les occurrences des triplets identiques."""
    seen: dict = {}
    for r in rows:
        if r.get("external_id"):
            continue
        triple = (r["booking_date"], r["label"].strip().lower(), r["amount"])
        occ = seen.get(triple, 0)
        seen[triple] = occ + 1
        r["external_id"] = _stable_external_id(r["booking_date"], r["label"], r["amount"], occ)
    return rows


# ---------------------------------------------------------------------------
# OFX
# ---------------------------------------------------------------------------

_OFX_TAG = re.compile(r"<([A-Z0-9.]+)>([^<\r\n]*)", re.IGNORECASE)


def _ofx_field(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def parse_ofx(content) -> list:
    """Parse un fichier OFX/QFX (SGML). Extrait chaque bloc <STMTTRN>."""
    text = _decode(content)
    blocks = re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, re.IGNORECASE | re.DOTALL)
    if not blocks:
        raise ParseError("Aucune transaction <STMTTRN> trouvée dans le fichier OFX.")
    currency = _ofx_field(text, "CURDEF") or "EUR"
    rows = []
    for block in blocks:
        dt = _ofx_field(block, "DTPOSTED") or _ofx_field(block, "DTUSER")
        amt = _ofx_field(block, "TRNAMT")
        name = _ofx_field(block, "NAME")
        memo = _ofx_field(block, "MEMO")
        fitid = _ofx_field(block, "FITID")
        if not dt or amt == "":
            continue
        label = name or memo or "Opération"
        rows.append({
            "external_id": f"ofx:{fitid}" if fitid else "",
            "booking_date": _norm_date(dt),
            "amount": _amount_to_cents(amt),
            "currency": currency,
            "label": label.strip(),
            "counterparty": (memo if name else "").strip(),
        })
    if not rows:
        raise ParseError("Fichier OFX sans transaction exploitable.")
    return _assign_external_ids(rows)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

_DATE_HEADERS = ("date", "date de comptabilisation", "date operation", "date d'opération",
                 "date de l'opération", "date valeur")
_LABEL_HEADERS = ("libelle", "libellé", "libelle operation", "libellé de l'opération",
                  "libelle simplifie", "nature de l'opération", "intitule", "designation")
_DEBIT_HEADERS = ("debit", "débit", "debit euros", "débit euros", "montant debit")
_CREDIT_HEADERS = ("credit", "crédit", "credit euros", "crédit euros", "montant credit")
_AMOUNT_HEADERS = ("montant", "montant euros", "montant (eur)", "montant en euros", "amount")


def _norm_header(h: str) -> str:
    return (h or "").strip().strip('"').lower()


def _match_col(headers: list, candidates) -> int:
    norm = [_norm_header(h) for h in headers]
    for i, h in enumerate(norm):
        if h in candidates:
            return i
    # Correspondance partielle (ex : « Débit euros » contient « débit »).
    for i, h in enumerate(norm):
        for c in candidates:
            if c and c in h:
                return i
    return -1


def _sniff_delimiter(sample: str) -> str:
    header_line = sample.splitlines()[0] if sample.splitlines() else sample
    counts = {d: header_line.count(d) for d in (";", "\t", ",")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ";"


def parse_csv(content) -> list:
    """Parse un CSV de relevé bancaire. Tolère un préambule (lignes d'en-tête
    de compte) avant la ligne de colonnes, détecte le séparateur et mappe les
    colonnes date / libellé / débit / crédit (ou une colonne montant unique)."""
    text = _decode(content)
    lines = [l for l in text.splitlines() if l.strip() != ""]
    if not lines:
        raise ParseError("Fichier CSV vide.")

    delimiter = _sniff_delimiter(text)

    # Localise la ligne d'en-tête : la première contenant une colonne date ET
    # (un libellé OU un montant). Les relevés CE ont souvent 1-N lignes de
    # préambule (titulaire, IBAN, solde) avant le tableau.
    header_idx = -1
    header_cells: list = []
    for i, line in enumerate(lines):
        cells = next(csv.reader([line], delimiter=delimiter))
        has_date = _match_col(cells, _DATE_HEADERS) != -1
        has_body = (_match_col(cells, _LABEL_HEADERS) != -1
                    or _match_col(cells, _AMOUNT_HEADERS) != -1
                    or _match_col(cells, _DEBIT_HEADERS) != -1
                    or _match_col(cells, _CREDIT_HEADERS) != -1)
        if has_date and has_body:
            header_idx = i
            header_cells = cells
            break
    if header_idx == -1:
        raise ParseError(
            "Impossible de repérer les colonnes du relevé (date, libellé, montant). "
            "Vérifie que le fichier est bien un export CSV de relevé bancaire."
        )

    ci_date = _match_col(header_cells, _DATE_HEADERS)
    ci_label = _match_col(header_cells, _LABEL_HEADERS)
    ci_debit = _match_col(header_cells, _DEBIT_HEADERS)
    ci_credit = _match_col(header_cells, _CREDIT_HEADERS)
    ci_amount = _match_col(header_cells, _AMOUNT_HEADERS)

    rows = []
    reader = csv.reader(lines[header_idx + 1:], delimiter=delimiter)
    for cells in reader:
        if not cells or all(c.strip() == "" for c in cells):
            continue

        def cell(idx):
            return cells[idx].strip() if 0 <= idx < len(cells) else ""

        raw_date = cell(ci_date)
        if not raw_date:
            continue
        try:
            booking_date = _norm_date(raw_date)
        except ParseError:
            # Ligne de total/solde résiduelle sans date valide : on ignore.
            continue

        if ci_amount != -1 and cell(ci_amount):
            amount = _amount_to_cents(cell(ci_amount))
        else:
            debit = _amount_to_cents(cell(ci_debit)) if ci_debit != -1 else 0
            credit = _amount_to_cents(cell(ci_credit)) if ci_credit != -1 else 0
            # Débit stocké en positif dans sa colonne → montant négatif.
            amount = credit - abs(debit)

        label = cell(ci_label) if ci_label != -1 else ""
        rows.append({
            "external_id": "",
            "booking_date": booking_date,
            "amount": amount,
            "currency": "EUR",
            "label": label or "Opération",
            "counterparty": "",
        })

    if not rows:
        raise ParseError("Aucune ligne d'opération exploitable dans le CSV.")
    return _assign_external_ids(rows)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def parse_statement(filename: str, content: bytes) -> list:
    """Choisit le parseur selon l'extension puis le contenu."""
    name = (filename or "").lower()
    head = _decode(content[:512]).lstrip().upper()
    is_ofx = name.endswith((".ofx", ".qfx")) or head.startswith("OFXHEADER") or "<OFX>" in head
    if is_ofx:
        return parse_ofx(content)
    return parse_csv(content)
