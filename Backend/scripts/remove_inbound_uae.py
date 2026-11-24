"""CLI runner to purge all deprecated Inbound UAE database records and bump caches.

Run inside Backend/:
    python -m scripts.remove_inbound_uae
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

for _env_file in (".env.local", ".env"):
    if os.path.exists(_env_file):
        load_dotenv(_env_file, override=False)

from config.database import engine
from services.cache_invalidation_service import CacheInvalidationService
from services.deprecated_team_purge import purge_deprecated_inbound_uae


def main() -> None:
    with engine.begin() as conn:
        counts = purge_deprecated_inbound_uae(conn)
    if counts:
        try:
            CacheInvalidationService.bump_data_and_config_version()
        except Exception:
            pass
    print(json.dumps({"purged": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
