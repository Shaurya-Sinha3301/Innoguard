import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from invoiceguard.api import schemas
from invoiceguard.api.auth import current_user, require_scope
from invoiceguard.api.deps import get_session
from invoiceguard.api.ratelimit import UPLOAD_GUARDS, WRITE_GUARDS
from invoiceguard.db import models as m
from invoiceguard.extraction.service import MAX_UPLOAD_BYTES
from invoiceguard.jobs.documents import replay_failed, submit_document
from invoiceguard.workflow.errors import IllegalTransition, InvoiceNotFound

router = APIRouter(tags=["documents"], dependencies=[Depends(require_scope("read"))])


@router.post(
    "/documents", response_model=schemas.InvoiceOut, status_code=202,
    dependencies=[Depends(require_scope("submit")), *UPLOAD_GUARDS],
)
async def upload_document(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: str = Depends(current_user),
) -> m.Invoice:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        return submit_document(session, data, filename=file.filename or "upload.pdf", actor=user)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/invoices/{invoice_id}/document")
def get_document(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> Response:
    doc = session.scalars(select(m.Document).where(m.Document.invoice_id == invoice_id)).first()
    if doc is None:
        raise HTTPException(404, "no document for this invoice")
    return Response(
        content=doc.data,
        media_type=doc.content_type,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.get("/invoices/{invoice_id}/extraction", response_model=list[schemas.ExtractionFieldOut])
def get_extraction(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> list[m.ExtractionField]:
    return list(
        session.scalars(
            select(m.ExtractionField)
            .where(m.ExtractionField.invoice_id == invoice_id)
            .order_by(m.ExtractionField.id)
        )
    )


@router.get("/failed-jobs", response_model=list[schemas.FailedJobOut])
def list_failed_jobs(
    session: Session = Depends(get_session),
    _user: str = Depends(current_user),
) -> list[m.FailedJob]:
    return list(
        session.scalars(
            select(m.FailedJob).where(m.FailedJob.status == "FAILED").order_by(m.FailedJob.id)
        )
    )


@router.post(
    "/invoices/{invoice_id}/replay", response_model=schemas.InvoiceOut,
    dependencies=[Depends(require_scope("review")), *WRITE_GUARDS],
)
def replay(
    invoice_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: str = Depends(current_user),
) -> m.Invoice:
    try:
        return replay_failed(session, invoice_id, actor=user)
    except InvoiceNotFound as exc:
        raise HTTPException(404, "invoice not found") from exc
    except IllegalTransition as exc:
        raise HTTPException(409, str(exc)) from exc
