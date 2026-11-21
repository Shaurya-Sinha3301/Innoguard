"""What a workflow pack is: a manifest (declarative) plus rules (Python).

The manifest describes what a reviewer sees and which numbers the rules use. It never
contains logic. Rules stay as ordinary, tested Python so a change to them is reviewed
like any other code change.
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session

from invoiceguard.domain.decision import Decision
from invoiceguard.extraction.records import NormalizedCase


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
    # Expenses: how far apart (in days) a receipt and its card transaction may be, and how
    # old a claim may be when it is submitted.
    date_window_days: int = 0
    max_claim_age_days: int = 0


class HowStep(_Spec):
    title: str
    text: str


class Manifest(_Spec):
    id: str
    name: str
    version: int
    description: str
    # The document this pack reads, shown on the upload screen.
    document: str
    # How the UI names things: one case ("invoice", "claim"), and the other party to it.
    case_noun: str = "case"
    counterparty: str = "Counterparty"
    # Three short steps shown to a new reviewer: what reads, what checks, what you decide.
    how_it_works: tuple["HowStep", ...] = ()
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


@dataclass(frozen=True)
class PackReconciliation:
    """What a pack's rules concluded for one case."""

    decision: Decision
    # Extra facts recorded on the audit event when the case reaches its outcome state.
    matched_payload: dict[str, Any]


class Pack(Protocol):
    """A registered workflow.

    The core (workflow, extraction, jobs, API) only talks to this interface, so it never
    names a pack. A pack supplies what is read from a document, how the read values are
    typed, how they are checked, and which reference data an agent may look up.
    """

    id: str
    manifest: Manifest
    # What the model must return, and how it is told to do it.
    extraction_model: type[BaseModel]
    system_prompt: str
    user_prompt: str
    # Names accepted by `lookup`, for agents.
    lookup_names: tuple[str, ...]

    def normalize(self, extracted: Any, file_hash: str) -> NormalizedCase:
        """Type the strings the model returned. Refuse what is ambiguous."""
        ...

    def apply_extracted(self, row: Any, value: Any) -> None:
        """Write the typed value onto the case row."""
        ...

    def reconcile(self, session: Session, row: Any, confidence: Decimal) -> PackReconciliation:
        """Check the case against reference data and decide."""
        ...

    def context(self, session: Session, row: Any) -> dict[str, Any]:
        """Pack-specific facts for the case page (what the case was checked against)."""
        ...

    def lookup(self, session: Session, name: str, key: str) -> Any:
        """Read-only reference data for agents."""
        ...
