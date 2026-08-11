from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_recovered_migration_graph_has_one_head() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["f5c2d7e8a901"]
    assert scripts.get_revision("e4a7c1d9b520").down_revision == "d9f4b6a1c230"
    assert scripts.get_revision("d9f4b6a1c230").down_revision == "c2f8a6d9e410"
    assert scripts.get_revision("e8c1a7d4b920").down_revision == "d5a7c9e2f410"
    assert scripts.get_revision("d5a7c9e2f410").down_revision == "ab31d8e7c4f2"
    assert scripts.get_revision("ab31d8e7c4f2").down_revision == "f9a3d6c8b271"
    assert scripts.get_revision("f9a3d6c8b271").down_revision == "e3b8c1d4f920"
    assert scripts.get_revision("c7e9a4b2d610").down_revision == "7f3c9a1d2e40"
    assert scripts.get_revision("a2d91f4c1b7e") is not None
    assert scripts.get_revision("b1f3d8e7a901") is not None
    assert scripts.get_revision("d4e8b7c1a920") is not None
    assert scripts.get_revision("f6c2a9d4e810").down_revision == (
        "a2d91f4c1b7e",
        "b1f3d8e7a901",
        "d4e8b7c1a920",
    )
