from repositories import json_repos


def test_missing_private_runtime_data_returns_default_without_writing_in_production(monkeypatch, tmp_path):
    monkeypatch.setattr(json_repos, "APP_ENV", "production")
    monkeypatch.setattr(json_repos, "DATA_DIR", str(tmp_path))
    json_repos._cache.clear()

    assert json_repos._load_json("employees.json", []) == []
    assert not (tmp_path / "employees.json").exists()


def test_missing_runtime_data_returns_default_without_hidden_development_write(monkeypatch, tmp_path):
    monkeypatch.setattr(json_repos, "APP_ENV", "development")
    monkeypatch.setattr(json_repos, "DATA_DIR", str(tmp_path))
    json_repos._cache.clear()

    assert json_repos._load_json("employees.json", []) == []
    assert not (tmp_path / "employees.json").exists()
