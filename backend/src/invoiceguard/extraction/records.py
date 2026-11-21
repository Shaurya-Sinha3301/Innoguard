"""What every pack's normaliser produces: typed values plus a record of each field read."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class FieldRecord:
    field: str
    value: str | None
    confidence: Decimal
    page: int | None
    snippet: str | None


@dataclass
class NormalizedCase:
    """`value` is the pack's typed object, or None when the document could not be read well
    enough to check (the case then goes to a person with the issues listed)."""

    value: Any | None
    confidence: Decimal
    fields: list[FieldRecord]
    issues: list[str] = field(default_factory=list)
