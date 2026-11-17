"""Prepare synthetic demo documents.

For each case: write the PO, receipts and vendor to the database, render the invoice PDF,
and store a *simulated* extraction in the replay cache, so the full pipeline can run with
no API key. Simulated records carry provider "fake" and model "fake-extractor", so they
can never be mistaken for real model output in the metrics.

    python -m invoiceguard.generator.demo_data --count 12 --out /app/extraction-cache/demo-pdfs
"""

import argparse
import random
from pathlib import Path

from invoiceguard.config import settings
from invoiceguard.db.session import SessionLocal
from invoiceguard.extraction.cache import CachedExtractor
from invoiceguard.extraction.fakes import FakeExtractor, truth_as_extraction
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.pdf import TEMPLATES, render_invoice_pdf
from invoiceguard.generator.seed import seed_master_data

DEMO_LABELS = (
    CaseLabel.CLEAN,
    CaseLabel.PRICE_VARIANCE,
    CaseLabel.PARTIAL_RECEIPT_OVERBILLED,
    CaseLabel.PARTIAL_RECEIPT_BILLED_CORRECTLY,
    CaseLabel.NO_RECEIPT,
    CaseLabel.HIGH_VALUE,
)


def prepare(count: int, out_dir: Path, start_index: int, cache_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with SessionLocal() as session:
        for i in range(count):
            index = start_index + i
            label = DEMO_LABELS[i % len(DEMO_LABELS)]
            template = TEMPLATES[i % len(TEMPLATES)]
            scenario = generate_scenario(random.Random(index), index, label)
            seed_master_data(session, scenario)
            pdf = render_invoice_pdf(scenario.invoice, template)
            simulated = FakeExtractor(truth_as_extraction(scenario.invoice, template))
            CachedExtractor(cache_dir, simulated).extract(pdf)
            path = out_dir / f"{index:05d}-{label.value.lower()}-{template}.pdf"
            path.write_bytes(pdf)
            written.append(path)
        session.commit()
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--start-index", type=int, default=90000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for path in prepare(
        args.count, args.out, args.start_index, Path(settings.extraction_cache_dir)
    ):
        print(path)


if __name__ == "__main__":
    main()
