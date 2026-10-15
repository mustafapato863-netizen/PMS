"""Generated Marketing KPI keys must fit the KPI key columns (PostgreSQL enforces VARCHAR(50); SQLite does not)."""

from models.models import KPIValue
from services.marketing_import_service import GENERATED_KPI_KEY_MAX_LENGTH, _generated_kpi_key


def test_limit_matches_the_kpi_values_column():
    assert KPIValue.__table__.c.kpi_key.type.length == GENERATED_KPI_KEY_MAX_LENGTH


def test_short_keys_are_unchanged():
    assert _generated_kpi_key("Media Buyer", "Reporting") == "mkt_media_buyer_reporting"


def test_long_keys_fit_and_stay_stable_and_distinct():
    long_key = _generated_kpi_key("Social Media Specialist", "Content calendar adherence")
    assert len(long_key) <= GENERATED_KPI_KEY_MAX_LENGTH
    assert long_key.startswith("mkt_social_media_specialist_content_")
    assert long_key == _generated_kpi_key("Social Media Specialist", "Content calendar adherence")
    other = _generated_kpi_key("Social Media Specialist", "Content calendar adherence rate")
    assert len(other) <= GENERATED_KPI_KEY_MAX_LENGTH
    assert other != long_key


def test_any_label_length_fits():
    for size in (1, 30, 46, 47, 60, 200):
        assert len(_generated_kpi_key("Account Manager", "x" * size)) <= GENERATED_KPI_KEY_MAX_LENGTH
