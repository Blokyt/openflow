"""Shared rate limiter instance — évite les imports circulaires entre main.py et les modules."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
