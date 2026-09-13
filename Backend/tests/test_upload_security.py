import io

import pytest
from fastapi import HTTPException, UploadFile
from openpyxl import Workbook

from config import settings
from services.upload_security import read_validated_excel


def _xlsx_bytes() -> bytes:
    workbook = Workbook()
    workbook.active["A1"] = "employee_id"
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_accepts_xlsx_signature():
    contents = _xlsx_bytes()
    upload = UploadFile(filename="performance.xlsx", file=io.BytesIO(contents))

    assert await read_validated_excel(upload) == contents


@pytest.mark.asyncio
async def test_sanitizes_client_filename():
    upload = UploadFile(filename="../../private/performance.xlsx", file=io.BytesIO(_xlsx_bytes()))

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
