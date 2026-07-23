"""API des transactions récurrentes.

Une récurrence est un modèle qui génère de vraies transactions à échéance
régulière (mensuelle, hebdomadaire, annuelle). Comme OpenFlow n'a pas de
planificateur, la génération est déclenchée à la demande (POST /run, appelé au
chargement de la page et disponible en bouton). Chaque récurrence garde
last_run_date pour ne jamais dupliquer une échéance.
"""
import calendar
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.core.auth import require_admin
from backend.core.database import get_conn, row_to_dict

router = APIRouter(dependencies=[Depends(require_admin)])

FREQUENCIES = ("weekly", "monthly", "yearly")
_MAX_PER_RUN = 120  # garde-fou anti-boucle / anti-backfill massif


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse(d: str) -> date:
    return datetime.strptime(d[:10], "%Y-%m-%d").date()


def _add_period(d: date, freq: str, n: int) -> date:
    """d + n périodes, en gardant le jour d'ancrage (clampé en fin de mois)."""
    if freq == "weekly":
        return d + timedelta(weeks=n)
    if freq == "yearly":
        year = d.year + n
        day = min(d.day, calendar.monthrange(year, d.month)[1])
        return date(year, d.month, day)
    # monthly
    total = d.month - 1 + n
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _due_dates(start: date, freq: str, last_run, end, today: date) -> list:
    """Échéances à générer : > last_run (ou >= start si jamais lancé), <= today,
    <= end si défini."""
    out = []
    n = 0
    while len(out) < _MAX_PER_RUN:
        d = _add_period(start, freq, n)
        n += 1
        if d > today or (end and d > end):
            break
        if (last_run is None and d >= start) or (last_run is not None and d > last_run):
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class RecurrencePayload(BaseModel):
    label: str
    description: str = ""
    amount_cents: int
    from_entity_id: int
    to_entity_id: int
    category_id: int | None = None
    contact_id: int | None = None
    frequency: str = "monthly"
    start_date: str
    end_date: str | None = None
    active: bool = True


def _get_or_404(conn, rec_id: int) -> dict:
    row = conn.execute("SELECT * FROM recurrences WHERE id = ?", (rec_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Récurrence introuvable")
    return row_to_dict(row)


def _validate(payload: RecurrencePayload):
    if not payload.label.strip():
        raise HTTPException(status_code=400, detail="Libellé requis")
    if payload.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="Le montant doit être positif")
    if payload.frequency not in FREQUENCIES:
        raise HTTPException(status_code=400, detail="Fréquence invalide")
    if payload.from_entity_id == payload.to_entity_id:
        raise HTTPException(status_code=400, detail="Les entités source et destination doivent différer")
    try:
        _parse(payload.start_date)
        if payload.end_date:
            _parse(payload.end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Date invalide")


@router.get("/")
def list_recurrences():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT r.*, fe.name AS from_entity_name, te.name AS to_entity_name, c.name AS category_name
               FROM recurrences r
               LEFT JOIN entities fe ON fe.id = r.from_entity_id
               LEFT JOIN entities te ON te.id = r.to_entity_id
               LEFT JOIN categories c ON c.id = r.category_id
               ORDER BY r.active DESC, r.label""",
        ).fetchall()
        return [row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/", status_code=201)
def create_recurrence(payload: RecurrencePayload):
    _validate(payload)
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO recurrences
               (label, description, amount_cents, from_entity_id, to_entity_id, category_id,
                contact_id, frequency, start_date, end_date, last_run_date, active, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
            (payload.label.strip(), payload.description.strip(), payload.amount_cents,
             payload.from_entity_id, payload.to_entity_id, payload.category_id, payload.contact_id,
             payload.frequency, payload.start_date[:10], payload.end_date[:10] if payload.end_date else None,
             1 if payload.active else 0, _now()),
        )
        conn.commit()
        return list_recurrences()
    finally:
        conn.close()


@router.put("/{rec_id}")
def update_recurrence(rec_id: int, payload: RecurrencePayload):
    _validate(payload)
    conn = get_conn()
    try:
        _get_or_404(conn, rec_id)
        conn.execute(
            """UPDATE recurrences SET label=?, description=?, amount_cents=?, from_entity_id=?,
               to_entity_id=?, category_id=?, contact_id=?, frequency=?, start_date=?, end_date=?, active=?
               WHERE id=?""",
            (payload.label.strip(), payload.description.strip(), payload.amount_cents,
             payload.from_entity_id, payload.to_entity_id, payload.category_id, payload.contact_id,
             payload.frequency, payload.start_date[:10], payload.end_date[:10] if payload.end_date else None,
             1 if payload.active else 0, rec_id),
        )
        conn.commit()
        return list_recurrences()
    finally:
        conn.close()


@router.delete("/{rec_id}")
def delete_recurrence(rec_id: int):
    conn = get_conn()
    try:
        _get_or_404(conn, rec_id)
        conn.execute("DELETE FROM recurrences WHERE id = ?", (rec_id,))
        conn.commit()
        return list_recurrences()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Génération des échéances dues
# ---------------------------------------------------------------------------

@router.post("/run")
def run_due():
    """Génère les transactions dues (échéances passées non encore créées) pour
    toutes les récurrences actives. Idempotent : ne recrée pas une échéance déjà
    générée (suivi via last_run_date)."""
    conn = get_conn()
    try:
        today = datetime.now(timezone.utc).date()
        now = _now()
        recs = conn.execute("SELECT * FROM recurrences WHERE active = 1").fetchall()
        generated = 0
        skipped = 0
        for row in recs:
            r = row_to_dict(row)
            # L'entité a pu être supprimée depuis la création de la récurrence, ou
            # être agrégée : on saute plutôt que d'insérer une transaction pointant
            # une entité fantôme/regroupement (noms NULL partout, incohérence).
            bad = False
            for eid in (r["from_entity_id"], r["to_entity_id"]):
                m = conn.execute("SELECT balance_mode FROM entities WHERE id = ?", (eid,)).fetchone()
                if m is None or m["balance_mode"] == "aggregate":
                    bad = True
                    break
            if bad:
                skipped += 1
                continue
            start = _parse(r["start_date"])
            last = _parse(r["last_run_date"]) if r["last_run_date"] else None
            end = _parse(r["end_date"]) if r["end_date"] else None
            dates = _due_dates(start, r["frequency"], last, end, today)
            if not dates:
                continue
            for d in dates:
                iso = d.isoformat()
                conn.execute(
                    """INSERT INTO transactions
                       (date, label, description, amount, category_id, contact_id, created_by,
                        created_at, updated_at, from_entity_id, to_entity_id)
                       VALUES (?, ?, ?, ?, ?, ?, 'récurrence', ?, ?, ?, ?)""",
                    (iso, r["label"], r["description"], r["amount_cents"], r["category_id"],
                     r["contact_id"], now, now, r["from_entity_id"], r["to_entity_id"]),
                )
                generated += 1
            conn.execute(
                "UPDATE recurrences SET last_run_date = ? WHERE id = ?",
                (dates[-1].isoformat(), r["id"]),
            )
        conn.commit()
        return {"generated": generated, "skipped": skipped}
    finally:
        conn.close()
