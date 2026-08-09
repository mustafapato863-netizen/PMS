import io

import pytest
from fastapi import UploadFile

from api.routers import upload as upload_router
from services import socket_service


class _DummySeeder:
    def process_uploaded_file(self, filename: str, contents: bytes, **_metadata):
        return {"records_imported": 1, "employees_imported": 1, "teams": ["Inbound", "Outbound"]}


@pytest.mark.asyncio
async def test_upload_success_does_not_crash_on_logging(monkeypatch):
    monkeypatch.setattr(upload_router, "DatabaseSeeder", _DummySeeder)
    monkeypatch.setattr(upload_router.CacheInvalidationService, "flush_all", staticmethod(lambda: None))

    async def _noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(socket_service.SocketNotificationService, "notify_file_upload", staticmethod(_noop_notify))

    upload_file = UploadFile(filename="PMS_Trend_All.xlsx", file=io.BytesIO(b"PK\x03\x04fake workbook"))

    response = await upload_router.upload_pms_file(file=upload_file, _user=object())

    assert response.success is True
    assert response.data["teams"] == ["Inbound", "Outbound"]
