"""Management batch delete reports what it could not delete.

The handler used to skip a failing batch silently and answer success. Now every requested id is accounted for:
removed batches in `data`, the ids whose delete raised in `failed_ids`, and a message with both counts.
"""

import asyncio
import json
import logging

import pytest
from fastapi.responses import JSONResponse

from api.routers import team_management
from api.routers.team_management import BatchDeleteManagementRequest, batch_delete_management_kpi_uploads
from services.cache_invalidation_service import CacheInvalidationService
from services.management_bsc_service import ManagementBSCService

IDS = ["batch-1", "batch-2", "batch-3"]


def _removed(batch_id: str) -> dict:
    return {
        "upload_batch_id": batch_id,
        "config_rows_deleted": 3,
        "snapshot_rows_deleted": 1,
        "history_rows_deleted": 0,
    }


@pytest.fixture
def delete_plan(monkeypatch):
    """Each test sets which ids raise. Other ids remove rows, as the real service does for a present batch."""
    plan = {"fail": set(), "missing": set(), "calls": []}

    def fake_delete(self, batch_id):
        plan["calls"].append(batch_id)
        if batch_id in plan["fail"]:
            raise RuntimeError(f"database error while deleting {batch_id}: 3 rows of contents")
        if batch_id in plan["missing"]:
            return {"upload_batch_id": batch_id, "config_rows_deleted": 0, "snapshot_rows_deleted": 0, "history_rows_deleted": 0}
        return _removed(batch_id)

    monkeypatch.setattr(ManagementBSCService, "delete_upload_batch", fake_delete)
    monkeypatch.setattr(CacheInvalidationService, "bump_config_version", staticmethod(lambda: None))
    return plan


def _call(ids: list[str]):
    request = BatchDeleteManagementRequest(upload_ids=ids)
    return asyncio.run(batch_delete_management_kpi_uploads(request, db=None, _user=None))


def test_all_removed_answers_success_with_no_failed_ids(delete_plan):
    body = _call(IDS)

    assert isinstance(body, dict)
    assert body["success"] is True
    assert [item["upload_batch_id"] for item in body["data"]] == IDS
    assert body["failed_ids"] == []
    assert body["message"] == "Deleted 3 of 3 management upload batches."


def test_some_failed_lists_only_the_failed_ids_in_request_order(delete_plan):
    delete_plan["fail"] = {"batch-2"}

    body = _call(IDS)

    assert body["success"] is True
    assert [item["upload_batch_id"] for item in body["data"]] == ["batch-1", "batch-3"]
    assert body["failed_ids"] == ["batch-2"]
    assert body["message"] == "Deleted 2 of 3 management upload batches. 1 could not be deleted."


def test_all_failed_answers_failure_with_the_single_delete_status(delete_plan):
    delete_plan["fail"] = set(IDS)

    response = _call(IDS)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["success"] is False
    assert body["data"] == []
    assert body["failed_ids"] == IDS
    assert body["message"] == "Deleted 0 of 3 management upload batches. 3 could not be deleted."
    assert body["detail"] == body["message"]


def test_an_id_with_no_rows_is_not_counted_as_removed_or_failed(delete_plan):
    delete_plan["missing"] = {"batch-1"}

    body = _call(["batch-1", "batch-2"])

    assert body["success"] is True
    assert body["failed_ids"] == []
    assert body["message"] == "Deleted 1 of 2 management upload batches."
    assert len(body["data"]) == 2


def test_each_failure_is_logged_by_id_without_the_contents(delete_plan, caplog):
    delete_plan["fail"] = {"batch-3"}

    with caplog.at_level(logging.ERROR, logger=team_management.logger.name):
        _call(IDS)

    failures = [record for record in caplog.records if record.levelno == logging.ERROR and "batch-3" in record.getMessage()]
    assert len(failures) == 1
    assert failures[0].exc_info is not None
    assert "could not be deleted" in failures[0].getMessage()
    assert all("batch-1" not in record.getMessage() for record in failures)


def test_request_contract_stays_one_to_one_hundred_ids():
    with pytest.raises(ValueError):
        BatchDeleteManagementRequest(upload_ids=[])
    with pytest.raises(ValueError):
        BatchDeleteManagementRequest(upload_ids=[f"b{index}" for index in range(101)])
