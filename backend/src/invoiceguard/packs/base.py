"""What a workflow pack is: a manifest (declarative) plus rules (Python).

The manifest describes what a reviewer sees and which numbers the rules use. It never
contains logic. Rules stay as ordinary, tested Python so a change to them is reviewed
like any other code change.
"""

from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReasonSpec(_Spec):
    code: str
    label: str
    explain: str
    # hard: blocks auto-approval whatever the model's confidence. soft: a signal only.
    severity: Literal["hard", "soft"] = "hard"


class FieldSpec(_Spec):
    name: str
    label: str
    type: Literal["text", "money", "date", "currency", "integer"] = "text"
    required: bool = True


class Thresholds(_Spec):
    min_extraction_confidence: Decimal
    min_match_quality: Decimal
    # Amounts above this always go to a human. None disables the rule.
    max_auto_amount: Decimal | None = None


class Tolerances(_Spec):
    price_pct: Decimal = Decimal("0")
    qty_pct: Decimal = Decimal("0")
    amount_abs: Decimal = Decimal("0")


class Manifest(_Spec):
    id: str
    name: str
    version: int
    description: str
    # The document this pack reads, shown on the upload screen.
    document: str
    fields: tuple[FieldSpec, ...]
    reasons: tuple[ReasonSpec, ...]
    # Reason codes that carry a field name after a colon, such as MISSING_FIELD:total.
    reason_prefixes: tuple[ReasonSpec, ...] = ()
    thresholds: Thresholds
    tolerances: Tolerances = Tolerances()
    # Which columns the queue shows and which cards the case page shows, in order.
    queue_columns: tuple[str, ...]
    detail_sections: tuple[str, ...]
    # A reason implied by any more specific one, so compact lists show it only when alone.
    implied_reason: str | None = None
    synthetic_data_notice: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> "Manifest":
        codes = [r.code for r in (*self.reasons, *self.reason_prefixes)]
        duplicates = sorted({c for c in codes if codes.count(c) > 1})
        if duplicates:
            raise ValueError(f"duplicate reason codes: {duplicates}")
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError("duplicate field names")
        if self.implied_reason and self.implied_reason not in codes:
            raise ValueError(f"implied_reason {self.implied_reason} is not a declared reason")
        return self


def load_manifest(path: Path) -> Manifest:
    with path.open(encoding="utf-8") as handle:
        return Manifest.model_validate(yaml.safe_load(handle))


class Pack(Protocol):
    """A registered workflow. Release 2 grows this protocol as the core becomes pack-driven."""

    id: str
    manifest: Manifest
