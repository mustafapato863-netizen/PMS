"""Importing basis test helpers must preserve the caller's CI policy."""
import importlib

import pytest


@pytest.mark.parametrize("module_name", [
    "tests.test_insights_basis_context",
    "tests.test_scoring_basis_comparison",
])
def test_basis_helper_import_preserves_ci(monkeypatch, module_name):
    monkeypatch.setenv("CI", "true")
    module = importlib.import_module(module_name)
    importlib.reload(module)
    import os
    assert os.environ["CI"] == "true"
