"""Startup notice for JSON files that earlier versions left in the data directory.

The runtime no longer reads or writes data/*.json. Those files can hold personal data, so the app only lists them and
logs one warning. It never opens them.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def obsolete_json_files(data_dir: str) -> list[str]:
    try:
        entries = os.scandir(data_dir)
    except OSError:
        return []
    with entries:
        return sorted(entry.name for entry in entries if entry.is_file() and entry.name.lower().endswith(".json"))


def warn_obsolete_json_files(data_dir: str) -> list[str]:
    names = obsolete_json_files(data_dir)
    if names:
        logger.warning(
            "Obsolete JSON data files in %s are not used by the app and can contain personal data; delete them: %s",
            data_dir,
            ", ".join(names),
        )
    return names
