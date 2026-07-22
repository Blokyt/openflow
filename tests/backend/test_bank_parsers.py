"""Tests des parseurs de relevés bancaires (OFX / CSV)."""
import pytest

from backend.modules.bank_reconciliation.parsers import (
    ParseError, parse_ofx, parse_csv, parse_statement, _amount_to_cents, _norm_date,
)


# ─── Helpers de conversion ────────────────────────────────────────────────────

def test_amount_fr_format():
    assert _amount_to_cents("1 250,00") == 125000
    assert _amount_to_cents("-1 250,50") == -125050
    assert _amount_to_cents("0,99") == 99
    assert _amount_to_cents("12") == 1200
    assert _amount_to_cents("") == 0


def test_amount_en_format_and_parentheses():
    assert _amount_to_cents("1,234.56") == 123456
    assert _amount_to_cents("(45,00)") == -4500
    assert _amount_to_cents("+80,00") == 8000


def test_amount_invalid_raises():
    with pytest.raises(ParseError):
        _amount_to_cents("abc")


def test_norm_date_formats():
    assert _norm_date("15/01/2026") == "2026-01-15"
    assert _norm_date("2026-01-15") == "2026-01-15"
    assert _norm_date("20260115") == "2026-01-15"
    assert _norm_date("20260115120000[+1:CET]") == "2026-01-15"


# ─── OFX ──────────────────────────────────────────────────────────────────────

OFX_SAMPLE = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
<CURDEF>EUR
<BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260115<TRNAMT>1250.00<FITID>ABC123<NAME>VIR RECU CLIENT<MEMO>facture</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260116<TRNAMT>-45.90<FITID>DEF456<NAME>ACHAT FOURNITURES</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


def test_parse_ofx_basic():
    rows = parse_ofx(OFX_SAMPLE)
    assert len(rows) == 2
    assert rows[0]["external_id"] == "ofx:ABC123"
    assert rows[0]["booking_date"] == "2026-01-15"
    assert rows[0]["amount"] == 125000
    assert rows[0]["label"] == "VIR RECU CLIENT"
    assert rows[0]["currency"] == "EUR"
    assert rows[1]["amount"] == -4590


def test_parse_ofx_is_idempotent_ids():
    """Deux parses du même fichier donnent les mêmes external_id (dédup stable)."""
    a = [r["external_id"] for r in parse_ofx(OFX_SAMPLE)]
    b = [r["external_id"] for r in parse_ofx(OFX_SAMPLE)]
    assert a == b == ["ofx:ABC123", "ofx:DEF456"]


def test_parse_ofx_empty_raises():
    with pytest.raises(ParseError):
        parse_ofx("<OFX></OFX>")


# ─── CSV Caisse d'Épargne ─────────────────────────────────────────────────────

CSV_CE = """Compte;FR76 1234
Solde au;01/01/2026;100,00
Date;Libellé;Débit;Crédit
15/01/2026;VIR RECU CLIENT;;1 250,00
16/01/2026;ACHAT FOURNITURES;45,90;
17/01/2026;PRLV EDF;80,00;
"""


def test_parse_csv_debit_credit_with_preamble():
    rows = parse_csv(CSV_CE)
    assert len(rows) == 3
    assert rows[0]["booking_date"] == "2026-01-15"
    assert rows[0]["amount"] == 125000          # crédit -> positif
    assert rows[0]["label"] == "VIR RECU CLIENT"
    assert rows[1]["amount"] == -4590           # débit -> négatif
    assert rows[2]["amount"] == -8000
    # external_id présent et stable
    assert all(r["external_id"].startswith("csv:") for r in rows)


def test_parse_csv_is_idempotent_ids():
    a = [r["external_id"] for r in parse_csv(CSV_CE)]
    b = [r["external_id"] for r in parse_csv(CSV_CE)]
    assert a == b


CSV_MONTANT = """Date,Libellé,Montant
15/01/2026,Cotisation,90.00
16/01/2026,Remboursement,-30.00
"""


def test_parse_csv_single_amount_column_comma_delim():
    rows = parse_csv(CSV_MONTANT)
    assert len(rows) == 2
    assert rows[0]["amount"] == 9000
    assert rows[1]["amount"] == -3000


def test_parse_csv_duplicate_lines_get_distinct_ids():
    """Deux lignes réellement identiques dans le même relevé -> ids distincts."""
    csv_dup = "Date;Libellé;Crédit\n15/01/2026;DON;10,00\n15/01/2026;DON;10,00\n"
    rows = parse_csv(csv_dup)
    assert len(rows) == 2
    assert rows[0]["external_id"] != rows[1]["external_id"]


def test_parse_csv_no_header_raises():
    with pytest.raises(ParseError):
        parse_csv("juste;du;texte\nsans;colonnes;bancaires\n")


# ─── Dispatch ─────────────────────────────────────────────────────────────────

def test_parse_statement_dispatch_by_extension():
    ofx_rows = parse_statement("releve.ofx", OFX_SAMPLE.encode("utf-8"))
    assert ofx_rows[0]["external_id"] == "ofx:ABC123"
    csv_rows = parse_statement("releve.csv", CSV_CE.encode("utf-8"))
    assert len(csv_rows) == 3


def test_parse_statement_dispatch_by_content():
    """Sans extension révélatrice, le contenu OFX est détecté."""
    rows = parse_statement("export", OFX_SAMPLE.encode("utf-8"))
    assert rows[0]["external_id"] == "ofx:ABC123"
