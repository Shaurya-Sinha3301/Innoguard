"""The locked evaluation set.

Cases are split by vendor template, not by random rows: two layouts are used while
developing, and the third ("ledger") is held out, so results on it show how extraction
handles a layout it was never tuned on. The case list is pinned by a SHA-256 hash; the
runner refuses to score a set whose content no longer matches its pin.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from invoiceguard.generator.cases import CaseLabel
from invoiceguard.generator.pdf import TEMPLATES

HELD_OUT_TEMPLATES = ("ledger",)
DEFAULT_PER_LABEL = 18


@dataclass(frozen=True)
class Case:
    case_id: str
    index: int
    label: str
    template: str
    split: str  # "dev" or "held_out"


def build_cases(per_label: int = DEFAULT_PER_LABEL) -> list[Case]:
    cases: list[Case] = []
    for label_no, label in enumerate(CaseLabel):
        for k in range(per_label):
            index = 100_000 + label_no * 1_000 + k
            template = TEMPLATES[k % len(TEMPLATES)]
            split = "held_out" if template in HELD_OUT_TEMPLATES else "dev"
            cases.append(
                Case(f"{label.value.lower()}-{k:03d}", index, label.value, template, split)
            )
    return cases


def content_hash(cases: list[Case]) -> str:
    canonical = json.dumps([asdict(c) for c in cases], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_locked(path: Path, cases: list[Case]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "description": "Locked evaluation set. Do not tune prompts or thresholds on it.",
        "held_out_templates": list(HELD_OUT_TEMPLATES),
        "sha256": content_hash(cases),
        "cases": [asdict(c) for c in cases],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class LockMismatch(Exception):
    pass


def load_locked(path: Path) -> list[Case]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = [Case(**c) for c in data["cases"]]
    if content_hash(cases) != data["sha256"]:
        raise LockMismatch(f"{path} was changed after it was locked")
    return cases


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Write the locked evaluation set")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--per-label", type=int, default=DEFAULT_PER_LABEL)
    args = parser.parse_args()
    write_locked(args.out, build_cases(args.per_label))
    print(f"wrote {args.out}")
