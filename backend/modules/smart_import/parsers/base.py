"""Base Parser class and ParseResult.

Each parser implements a strategy to extract transactions from a file.
Multiple parsers are tried against each upload; the user picks the best result.

Contract:
- A Parser is a class with id, name, supported_extensions.
- Static method `detect(file_path, ext)` returns a confidence score 0.0-1.0.
- Method `parse(file_path)` returns a list of TransactionDraft.

To add a new parser: drop a .py file in parsers/ exporting a `parser` instance.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TransactionDraft:
    """A parsed transaction, before matching against the DB."""
    date: str  # YYYY-MM-DD
    label: str
    amount: float  # positive = income, negative = expense
    description: str = ""
    category_hint: str = ""  # text from source, to be mapped later
    from_entity_hint: str = ""
    to_entity_hint: str = ""
    raw: dict = field(default_factory=dict)  # original row data


@dataclass
class ParseResult:
    """Result of running one parser against a file."""
    parser_id: str
    parser_name: str
    confidence: float  # 0.0 to 1.0
    transactions: list[TransactionDraft] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)  # parser-specific info (sheet names, columns detected...)


class Parser:
    id: str = "base"
    name: str = "Base Parser"
    description: str = ""
    supported_extensions: list[str] = []

    @staticmethod
    def detect(file_path: str, ext: str) -> float:
        """Return a confidence score 0.0 to 1.0 indicating how likely this parser can handle the file.

        Override in subclasses. Default: 0 if extension doesn't match, 0.1 otherwise.
        """
        return 0.0

    def parse(self, file_path: str) -> ParseResult:
        """Parse the file and return transactions."""
        raise NotImplementedError
