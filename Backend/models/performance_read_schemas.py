"""Typed contracts for the bounded performance dashboard read API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PerformancePeriod(BaseModel):
    key: str
    month: str
    year: int


class PerformanceScope(BaseModel):
    period: str
    team: str | None = None
    performance_level: str | None = None
    region: str | None = None
    position: str | None = None
    location: str | None = None


class PerformanceCatalogData(BaseModel):
    periods: list[dict[str, Any]] = Field(default_factory=list)
    months: list[str] = Field(default_factory=list)
    scopes: list[dict[str, Any]] = Field(default_factory=list)
    data_version: int = 0
    as_of: str


class PerformanceSummaryData(BaseModel):
    scope: PerformanceScope
    period: PerformancePeriod
    previous_period: PerformancePeriod | None = None
    current: dict[str, Any] = Field(default_factory=dict)
    previous: dict[str, Any] | None = None
    trend: list[dict[str, Any]] = Field(default_factory=list)
    team_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    data_version: int = 0
    as_of: str


class PerformanceRecordPage(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    page_size: int
    next_cursor: str | None = None
    has_more: bool = False
    total: int | None = None
    data_version: int = 0
    as_of: str

