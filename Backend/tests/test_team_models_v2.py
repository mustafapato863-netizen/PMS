"""Characterize team model behavior after the Pydantic v2 migration."""

import pytest
from pydantic import ValidationError

from models.team_models import (
    TeamConfig,
    TeamCreateRequest,
    TeamResponse,
    TeamUpdateRequest,
    TeamValidationResponse,
)


def test_create_request_keeps_canonical_team_name():
    request = TeamCreateRequest(name="Inbound Call Center", display_name="Inbound")
    assert request.name == "inbound_call_center"


def test_kpi_weights_accept_valid_sum_and_reject_invalid_sum():
    request = TeamUpdateRequest(kpi_weights={"quality": 0.4, "quantity": 0.6})
    assert request.kpi_weights == {"quality": 0.4, "quantity": 0.6}
    with pytest.raises(ValidationError, match="KPI weights must sum"):
        TeamUpdateRequest(kpi_weights={"quality": 0.2, "quantity": 0.3})
    with pytest.raises(ValidationError, match="KPI weights must sum"):
        TeamConfig(name="test", display_name="Test", kpi_weights={"quality": 0.4})


def test_optional_update_does_not_require_weights():
    assert TeamUpdateRequest().kpi_weights is None


def test_schema_examples_are_exposed_in_pydantic_v2():
    assert TeamConfig.model_json_schema()["example"]["name"] == "inbound"
    assert TeamValidationResponse.model_json_schema()["example"]["valid"] is True


def test_orm_attribute_validation_is_enabled_for_team_response():
    assert TeamResponse.model_config.get("from_attributes") is True
