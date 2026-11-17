"""Load synthetic demo invoices into a running system.

For each case it writes the PO, receipts and vendor, renders the invoice PDF, stores a
*simulated* extraction (provider "fake", model "fake-extractor") so the pipeline runs with
no API key, and optionally submits the PDF through the normal upload path. Nothing here is
real data, and the simulated records can never be mistaken for model output.

    python -m invoiceguard.generator.demo_data --count 12 --submit
    python -m invoiceguard.generator.demo_data --count 6 --out /app/extraction-cache/demo-pdfs
"""

import argparse
import dataclasses
import random
from pathlib import Path

from invoiceguard.db.session import SessionLocal
from invoiceguard.extraction.cache import record
from invoiceguard.extraction.fakes import FakeExtractor, truth_as_extraction
from invoiceguard.generator.cases import CaseLabel, generate_scenario
from invoiceguard.generator.pdf import TEMPLATES, render_invoice_pdf
from invoiceguard.generator.seed import seed_master_data
from invoiceguard.jobs.documents import submit_document

DEMO_LABELS = (
    CaseLabel.CLEAN,
    CaseLabel.PRICE_VARIANCE,
    CaseLabel.PARTIAL_RECEIPT_OVERBILLED,
    CaseLabel.PARTIAL_RECEIPT_BILLED_CORRECTLY,
    CaseLabel.NO_RECEIPT,
    CaseLabel.HIGH_VALUE,
    CaseLabel.QTY_OVER_ORDERED,
    CaseLabel.VENDOR_MISMATCH,
)


def prepare(count: int, start_index: int, *, submit: bool, out_dir: Path | None) -> list[str]:
    done: list[str] = []
    for i in range(count):
        index = start_index + i
        label = DEMO_LABELS[i % len(DEMO_LABELS)]
        template = TEMPLATES[i % len(TEMPLATES)]
        scenario = generate_scenario(random.Random(index), index, label)
        # The demo has no duplicate cases, so leave out the placeholder "existing" invoices.
        scenario = dataclasses.replace(scenario, existing_invoices=())
        pdf = render_invoice_pdf(scenario.invoice, template)
        simulated = FakeExtractor(truth_as_extraction(scenario.invoice, template)).extract(pdf)
        record(SessionLocal, pdf, simulated, simulated=True)

        with SessionLocal() as session:
            seed_master_data(session, scenario)
            if submit:
                submit_document(
                    session,
                    pdf,
                    filename=f"{scenario.invoice.invoice_number}.pdf",
                    actor="demo-loader",
                    template_id=template,
                )
            session.commit()

        name = f"{index:05d}-{label.value.lower()}-{template}.pdf"
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / name).write_bytes(pdf)
        done.append(name)
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description="Load synthetic demo invoices")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--start-index", type=int, default=90000)
    parser.add_argument("--submit", action="store_true", help="upload each PDF for processing")
    parser.add_argument("--out", type=Path, default=None, help="also write the PDFs here")
    args = parser.parse_args()
    for name in prepare(args.count, args.start_index, submit=args.submit, out_dir=args.out):
        print(name)


if __name__ == "__main__":
    main()
