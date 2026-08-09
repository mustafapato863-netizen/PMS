from pathlib import Path

from fastapi import HTTPException, UploadFile

from config import settings


_XLSX_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_XLS_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


async def read_validated_excel(
    file: UploadFile,
    *,
    allowed_extensions: tuple[str, ...] = (".xlsx", ".xls"),
) -> bytes:
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        accepted = ", ".join(allowed_extensions)
        raise HTTPException(status_code=400, detail=f"Only {accepted} files are accepted.")
    file.filename = filename

    # Documented Vercel Production Limit: Vercel serverless functions have a strict 4.5 MB request body limit.
    # We validate this upfront to avoid opaque 500 crashes and return a clean 413 Payload Too Large.
    contents = await file.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        limit_mb = settings.MAX_UPLOAD_BYTES / (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"Upload exceeds the {limit_mb:g} MB limit. Vercel production limits request bodies to 4.5 MB.")
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    valid_signature = (
        extension == ".xlsx" and contents.startswith(_XLSX_SIGNATURES)
    ) or (
        extension == ".xls" and contents.startswith(_XLS_SIGNATURE)
    )
    if not valid_signature:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid Excel workbook.")
    return contents
