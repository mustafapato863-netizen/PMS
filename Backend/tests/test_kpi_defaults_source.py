"""Weights and targets come from the code defaults when nothing is stored. Pharmacy Prescription is a contribution share
(0.07), and the root-cause target falls back to DEFAULT_TARGETS, not to a literal. Synthetic data only."""

from types import SimpleNamespace

import importlib.util
from services.analysis_service import AnalysisService
from services.kpi_service import DEFAULT_TARGETS, KPIService


class _TargetsRepo:
    def __init__(self, targets):
        self._targets = targets

    def get_by_team(self, team):
        return SimpleNamespace(targets=self._targets) if self._targets is not None else None


def _attend_is_the_root_cause(service):
    achievements = {"Attend": 0.5, "Booking": 0.9}
    weights = {"Attend": 0.7, "Booking": 0.1}
    row = {"A.Attend%": 0.5, "A.Booking%": 0.9}
    return service.run_root_cause_analysis("Outbound", achievements, weights, row)


def test_pharmacy_prescription_default_is_the_contribution_share():
    assert DEFAULT_TARGETS["Pharmacy"]["Prescription"] == 0.07


def test_root_cause_target_falls_back_to_the_default_when_nothing_is_stored():
    root = _attend_is_the_root_cause(AnalysisService())
    assert root.kpi == "Attend"
    assert root.target == DEFAULT_TARGETS["Outbound"]["Attend"] == 0.55


def test_a_stored_target_overrides_the_default_for_its_key_only():
    root = _attend_is_the_root_cause(AnalysisService(_TargetsRepo({"Attend": 0.8})))
    assert root.target == 0.8


def test_kpi_service_without_repositories_uses_the_code_defaults():
    service = KPIService()
    assert service.weights_repo is None and service.targets_repo is None


def test_the_json_repository_module_is_gone():
    assert importlib.util.find_spec("repositories.json_repos") is None
