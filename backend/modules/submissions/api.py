"""Soumissions de transactions : les trésoriers proposent, l'admin valide."""
from fastapi import APIRouter

router = APIRouter()

VALID_STATUSES = {"pending", "approved", "rejected", "cancelled"}
