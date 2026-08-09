import json
from pathlib import Path

from config import loader


def test_team_config_cache_returns_isolated_values():
    loader.clear_configuration_cache()

    first = loader.load_team_config("Coding")
    before = loader._load_validated_config_cached.cache_info()
    second = loader.load_team_config("Coding")
    after = loader._load_validated_config_cached.cache_info()

    assert first == second
    assert first is not second
    assert after.hits == before.hits + 1

    first["team"] = "mutated by caller"
    assert loader.load_team_config("Coding")["team"] == "Coding"


def test_all_team_configs_reuse_file_cache():
    loader.clear_configuration_cache()

    first = loader.load_all_team_configs()
    before = loader._load_validated_config_cached.cache_info()
    second = loader.load_all_team_configs()
    after = loader._load_validated_config_cached.cache_info()

    assert first == second
    assert first is not second
    assert after.hits >= before.hits + len(first)


def test_all_loaded_kpis_use_global_100_percent_cap():
    loader.clear_configuration_cache()

    configs = loader.load_all_team_configs()
    assert configs
    for config in configs:
        assert config.get("capping") == "capped_at_100"
        kpi_groups = [config.get("kpis", [])]
        for level_config in config.get("performance_levels", {}).values():
            kpi_groups.append(level_config.get("kpis", []))
            kpi_groups.extend(
                position_config.get("kpis", [])
                for position_config in level_config.get("positions", {}).values()
            )
        kpis = [kpi for group in kpi_groups for kpi in group]
        assert kpis, config.get("team")
        assert all(kpi.get("cap_achievement") is True for kpi in kpis)


def test_config_file_change_uses_a_new_cache_version(tmp_path):
    source = Path(loader.__file__).parent / "teams" / "coding.json"
    config_path = tmp_path / "coding.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    config_path.write_text(json.dumps(config), encoding="utf-8")

    loader.clear_configuration_cache()
    first = loader._load_config_file(config_path)
    before = loader._load_validated_config_cached.cache_info()

    config["_cache_probe"] = "changed"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    second = loader._load_config_file(config_path)
    after = loader._load_validated_config_cached.cache_info()

    assert "_cache_probe" not in first
    assert second["_cache_probe"] == "changed"
    assert after.misses == before.misses + 1
