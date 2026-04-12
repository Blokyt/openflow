"""FEC Export API module for OpenFlow.

Generates the Fichier des Ecritures Comptables (FEC) — the official French
accounting export format required by tax authorities.
"""
import csv
import io
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.core.database import get_conn

router = APIRouter()

FEC_HEADERS = [
    "JournalCode",
    "JournalLib",
    "EcritureNum",
    "EcritureDate",
    "CompteNum",
    "CompteLib",
    "CompAuxNum",
    "CompAuxLib",
    "PieceRef",
    "PieceDate",
    "EcritureLib",
    "Debit",
    "Credit",
    "EcrtureLet",
    "DateLet",
    "ValidDate",
    "MontantDevise",
    "Idevise",
]


def _format_date(date_str: str) -> str:
    """Convert YYYY-MM-DD to YYYYMMDD for FEC format."""
    if not date_str:
        return ""
    return date_str.replace("-", "")


def _transaction_to_fec_row(tx: dict, index: int) -> dict:
    """Map a transaction dict to a FEC row dict."""
    amount = float(tx.get("amount", 0))
    is_income = amount >= 0
    abs_amount = abs(amount)

    journal_code = "VE" if is_income else "AC"
    journal_lib = "Ventes" if is_income else "Achats"
    compte_num = "411000" if is_income else "401000"
    compte_lib = "Clients" if is_income else "Fournisseurs"

    date_formatted = _format_date(tx.get("date", ""))
    ecriture_num = f"{journal_code}{index:06d}"

    return {
        "JournalCode": journal_code,
        "JournalLib": journal_lib,
        "EcritureNum": ecriture_num,
        "EcritureDate": date_formatted,
        "CompteNum": compte_num,
        "CompteLib": compte_lib,
        "CompAuxNum": "",
        "CompAuxLib": "",
        "PieceRef": str(tx.get("id", "")),
        "PieceDate": date_formatted,
        "EcritureLib": tx.get("label", ""),
        "Debit": f"{abs_amount:.2f}" if is_income else "0.00",
        "Credit": "0.00" if is_income else f"{abs_amount:.2f}",
        "EcrtureLet": "",
        "DateLet": "",
        "ValidDate": date_formatted,
        "MontantDevise": "",
        "Idevise": "",
    }


@router.get("/generate")
def generate_fec(fiscal_year: Optional[int] = None):
    """Generate a FEC (Fichier des Ecritures Comptables) CSV export.

    Query params:
        fiscal_year: filter transactions to that calendar year (e.g. 2025).
                     If omitted, all transactions are included.
    """
    conn = get_conn()
    try:
        query = "SELECT * FROM transactions WHERE 1=1"
        params: list = []
        if fiscal_year is not None:
            query += " AND date >= ? AND date <= ?"
            params.append(f"{fiscal_year}-01-01")
            params.append(f"{fiscal_year}-12-31")
        query += " ORDER BY date ASC, id ASC"
        cur = conn.execute(query, params)
        transactions = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=FEC_HEADERS,
        delimiter="|",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for i, tx in enumerate(transactions, start=1):
        writer.writerow(_transaction_to_fec_row(tx, i))

    output.seek(0)
    content = output.read()

    filename = f"FEC_{fiscal_year}.csv" if fiscal_year else "FEC.csv"

    def iter_content():
        yield content

    return StreamingResponse(
        iter_content(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
