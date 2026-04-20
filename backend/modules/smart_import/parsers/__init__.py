"""Auto-discover parsers in this package.

Each parser module must export a module-level `parser` instance.
"""
import importlib
import pkgutil
from pathlib import Path

from .base import Parser, ParseResult, TransactionDraft

_PACKAGE_DIR = Path(__file__).parent


def get_all_parsers() -> list[Parser]:
    """Discover and instantiate all Parser subclasses in this package."""
    parsers = []
    for _, name, _ in pkgutil.iter_modules([str(_PACKAGE_DIR)]):
        if name in ("base", "__init__"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
            if hasattr(mod, "parser") and isinstance(mod.parser, Parser):
                parsers.append(mod.parser)
        except Exception as e:
            print(f"Warning: failed to load parser '{name}': {e}")
    return parsers


__all__ = ["Parser", "ParseResult", "TransactionDraft", "get_all_parsers"]
