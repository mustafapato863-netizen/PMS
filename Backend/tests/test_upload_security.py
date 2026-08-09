import io

import pytest
from fastapi import HTTPException, UploadFile

from config import settings
from services.upload_security import read_validated_excel


@pytest.mark.asyncio
async def test_accepts_xlsx_signature():
    upload = UploadFile(filename="performance.xlsx", file=io.BytesIO(b"PK\x03\x04content"))

    assert await read_validated_excel(upload) == b"PK\x03\x04content"


@pytest.mark.asyncio
async def test_sanitizes_client_filename():
    upload = UploadFile(filename="../../private/performance.xlsx", file=io.BytesIO(b"PK\x03\x04content"))

    await read_validated_excel(upload)

    assert upload.filename == "performance.xlsx"


@pytest.mark.asyncio
async def test_rejects_extension_spoofing():
    upload = UploadFile(filename="performance.xlsx", file=io.BytesIO(b"not an excel file"))

    with pytest.raises(HTTPException) as exc_info:
        await read_validated_excel(upload)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 8)
    upload = UploadFile(filename="performance.xlsx", file=io.BytesIO(b"PK\x03\x04too-large"))

    with pytest.raises(HTTPException) as exc_info:
        await read_validated_excel(upload)

    assert exc_info.value.status_code == 413
