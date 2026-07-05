"""Verrouillage progressif du login après échecs répétés.

Deux compteurs indépendants d'échecs consécutifs (depuis le dernier succès) :
par email (seuil bas, protège un compte ciblé) et par adresse IP (seuil haut,
contre le balayage de comptes). Au-delà du seuil, le délai double à chaque
échec supplémentaire, plafonné à 30 minutes, décompté depuis le dernier échec.
Un login réussi remet le compteur à zéro. La table login_events sert aussi de
journal des connexions consultable par l'admin.
"""
from datetime import datetime, timezone

EMAIL_THRESHOLD = 5
IP_THRESHOLD = 15
BASE_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 30 * 60


def _consecutive_failures(conn, field: str, value: str):
    """(nombre d'échecs consécutifs depuis le dernier succès, date du dernier échec)."""
    assert field in ("email", "ip")
    rows = conn.execute(
        f"SELECT success, created_at FROM login_events WHERE {field} = ? "
        "ORDER BY id DESC LIMIT 200",
        (value,),
    ).fetchall()
    count, last_failure_at = 0, None
    for row in rows:
        if row["success"]:
            break
        if last_failure_at is None:
            last_failure_at = row["created_at"]
        count += 1
    return count, last_failure_at


def _remaining(count: int, threshold: int, last_failure_at, now: datetime) -> int:
    if count < threshold or last_failure_at is None:
        return 0
    delay = min(BASE_DELAY_SECONDS * (2 ** (count - threshold)), MAX_DELAY_SECONDS)
    elapsed = (now - datetime.fromisoformat(last_failure_at)).total_seconds()
    return max(0, int(delay - elapsed))


def lockout_remaining_seconds(conn, email: str, ip: str) -> int:
    """Secondes de verrouillage restantes pour ce couple (email, IP), 0 si libre."""
    now = datetime.now(timezone.utc)
    count_e, last_e = _consecutive_failures(conn, "email", email)
    count_i, last_i = _consecutive_failures(conn, "ip", ip)
    return max(
        _remaining(count_e, EMAIL_THRESHOLD, last_e, now),
        _remaining(count_i, IP_THRESHOLD, last_i, now),
    )


def record_login_event(conn, email: str, ip: str, success: bool, user_agent: str = "") -> None:
    """Journalise une tentative de connexion (l'appelant commite)."""
    conn.execute(
        "INSERT INTO login_events (email, ip, success, created_at, user_agent) "
        "VALUES (?, ?, ?, ?, ?)",
        (email, ip, 1 if success else 0,
         datetime.now(timezone.utc).isoformat(), user_agent[:256]),
    )
