"""Photos and files the owner sends in the chat (docs/ANEXOS.md)."""

import uuid

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from pydantic import BaseModel

from apps.api.deps import CurrentUser, DbSession
from core.conversation import attachments
from infrastructure.database.models import Attachment

router = APIRouter(prefix="/attachments", tags=["attachments"])

# Read one byte past the larger limit, so an oversized upload is refused without reading it all.
_READ_LIMIT = max(attachments.MAX_IMAGE_BYTES, attachments.MAX_DOCUMENT_BYTES) + 1


class AttachmentOut(BaseModel):
    id: uuid.UUID
    kind: str
    filename: str
    media_type: str
    size_bytes: int
    # Whether any text could be read out of a document (None for photos).
    readable: bool | None = None


def attachment_out(attachment: Attachment) -> AttachmentOut:
    return AttachmentOut(
        id=attachment.id,
        kind=attachment.kind,
        filename=attachment.filename,
        media_type=attachment.media_type,
        size_bytes=attachment.size_bytes,
        readable=None
        if attachment.kind == "image"
        else bool((attachment.extracted_text or "").strip()),
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile, db: DbSession, user: CurrentUser) -> AttachmentOut:
    data = await file.read(_READ_LIMIT)
    if len(data) >= _READ_LIMIT:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Arquivo grande demais (máximo 10 MB)."
        )
    try:
        stored = attachments.store(db, user.id, file.filename, data)
    except attachments.AttachmentRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return attachment_out(stored)


@router.get("/{attachment_id}")
def download(attachment_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anexo não encontrado")
    return Response(
        content=attachment.data,
        # Photos were checked by their bytes; anything else is served as a download, never run.
        media_type=attachment.media_type
        if attachment.kind == "image"
        else "application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
