"""Utilitaires de formatage partagés entre modules."""
from datetime import date


def format_date_fr(iso_date: str) -> str:
    """Formate une date ISO (AAAA-MM-JJ) en JJ/MM/AAAA pour l'affichage utilisateur.

    Retombe sur la chaîne d'origine si non parsable.
    """
    try:
        return date.fromisoformat(iso_date).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso_date
