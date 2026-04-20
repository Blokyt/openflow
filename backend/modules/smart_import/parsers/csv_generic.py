"""Generic CSV parser with column auto-detection.

Detects columns by header names (date, libellé, montant, catégorie...) in French and English.
Handles common separators (,;|\\t) and amount formats (1 234,56 / 1,234.56 / -123.45).
"""
import csv
import io
import re
from datetime import datetime

from .base import Parser, ParseResult, TransactionDraft


DATE_ALIASES = ["date", "datum", "jour"]
LABEL_ALIASES = ["libellé", "libelle", "label", "description", "motif", "intitulé", "intitule", "objet"]
AMOUNT_ALIASES = ["montant", "amount", "somme", "valeur"]
DEBIT_ALIASES = ["dépense", "depense", "débit", "debit", "sortie"]
CREDIT_ALIASES = ["recette", "crédit", "credit", "entrée", "entree", "revenu"]
CATEGORY_ALIASES = ["catégorie", "categorie", "category", "cat", "type"]


def _normalize(s):
    return str(s or "").strip().lower()


def _detect_separator(sample: str) -> str:
    """Detect CSV separator by counting occurrences in first lines."""
    first_lines = sample.split("\n")[:5]
    candidates = [",", ";", "\t", "|"]
    scores = {sep: sum(line.count(sep) for line in first_lines) for sep in candidates}
    return max(scores, key=scores.get)


def _parse_amount(s: str) -> float | None:
    """Parse amount like '1 234,56' or '1,234.56' or '-123.45 €'."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    # Remove currency symbols and spaces
    s = re.sub(r"[€$£\s]", "", s)
    # French format: "1234,56" → "1234.56"
    # US format: "1,234.56" → "1234.56"
    if "," in s and "." in s:
        # Assume US: comma = thousands, dot = decimal
        s = s.replace(",", "")
    elif "," in s:
        # Assume French: comma = decimal
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(s: str) -> str | None:
    """Parse date in various formats → YYYY-MM-DD."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class CsvGenericParser(Parser):
    id = "csv_generic"
    name = "CSV générique"
    description = "CSV avec détection automatique des colonnes (date, libellé, montant...)"
    supported_extensions = [".csv", ".tsv", ".txt"]

    @staticmethod
    def detect(file_path: str, ext: str) -> float:
        if ext not in (".csv", ".tsv", ".txt"):
            return 0.0
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample = f.read(4096)
        except Exception:
            return 0.0

        if not sample.strip():
            return 0.0

        sep = _detect_separator(sample)
        reader = csv.reader(io.StringIO(sample), delimiter=sep)
        try:
            header = next(reader)
        except StopIteration:
            return 0.0

        if len(header) < 2:
            return 0.0

        norm = [_normalize(h) for h in header]
        has_date = any(any(a in h for a in DATE_ALIASES) for h in norm)
        has_label = any(any(a in h for a in LABEL_ALIASES) for h in norm)
        has_amount = (
            any(any(a in h for a in AMOUNT_ALIASES) for h in norm)
            or (any(any(a in h for a in DEBIT_ALIASES) for h in norm)
                and any(any(a in h for a in CREDIT_ALIASES) for h in norm))
        )

        score = 0.3  # base for valid CSV
        if has_date: score += 0.3
        if has_label: score += 0.2
        if has_amount: score += 0.3
        return min(score, 1.0)

    def parse(self, file_path: str) -> ParseResult:
        result = ParseResult(parser_id=self.id, parser_name=self.name, confidence=0.8)

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            result.errors.append(f"Impossible de lire le fichier: {e}")
            return result

        sep = _detect_separator(content[:4096])
        reader = csv.reader(io.StringIO(content), delimiter=sep)
        try:
            header = next(reader)
        except StopIteration:
            result.errors.append("Fichier vide")
            return result

        norm = [_normalize(h) for h in header]

        # Find column indices
        def find_col(aliases):
            for i, h in enumerate(norm):
                if any(a in h for a in aliases):
                    return i
            return None

        idx_date = find_col(DATE_ALIASES)
        idx_label = find_col(LABEL_ALIASES)
        idx_amount = find_col(AMOUNT_ALIASES)
        idx_debit = find_col(DEBIT_ALIASES)
        idx_credit = find_col(CREDIT_ALIASES)
        idx_cat = find_col(CATEGORY_ALIASES)

        if idx_date is None:
            result.errors.append("Colonne 'date' introuvable")
            return result
        if idx_label is None:
            result.errors.append("Colonne 'libellé' introuvable")
            return result
        if idx_amount is None and (idx_debit is None or idx_credit is None):
            result.errors.append("Colonne 'montant' (ou 'débit'+'crédit') introuvable")
            return result

        result.meta = {
            "separator": repr(sep),
            "columns": {
                "date": header[idx_date] if idx_date is not None else None,
                "label": header[idx_label] if idx_label is not None else None,
                "amount": header[idx_amount] if idx_amount is not None else None,
                "debit": header[idx_debit] if idx_debit is not None else None,
                "credit": header[idx_credit] if idx_credit is not None else None,
                "category": header[idx_cat] if idx_cat is not None else None,
            },
        }

        for row_idx, row in enumerate(reader, start=2):
            if not row or all(not c.strip() for c in row):
                continue
            try:
                date_str = _parse_date(row[idx_date])
                if not date_str:
                    result.warnings.append(f"Ligne {row_idx}: date invalide")
                    continue

                label_str = str(row[idx_label]).strip() if idx_label < len(row) else ""
                if not label_str:
                    continue

                if idx_amount is not None:
                    amount = _parse_amount(row[idx_amount] if idx_amount < len(row) else "")
                    if amount is None:
                        continue
                else:
                    dep = _parse_amount(row[idx_debit] if idx_debit < len(row) else "") or 0.0
                    rec = _parse_amount(row[idx_credit] if idx_credit < len(row) else "") or 0.0
                    amount = -abs(dep) if dep > 0 else rec

                if amount == 0:
                    continue

                cat_str = ""
                if idx_cat is not None and idx_cat < len(row):
                    cat_str = str(row[idx_cat]).strip()

                result.transactions.append(TransactionDraft(
                    date=date_str,
                    label=label_str,
                    amount=amount,
                    category_hint=cat_str,
                    raw={"row": row_idx},
                ))
            except (IndexError, ValueError) as e:
                result.warnings.append(f"Ligne {row_idx}: {e}")
                continue

        return result


parser = CsvGenericParser()
