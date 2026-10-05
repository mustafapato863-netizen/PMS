"""Process-level healthcheck for the async worker (no HTTP server).

The backend image HEALTHCHECK probes an HTTP liveness URL. The worker runs
`python worker.py` and never binds that port, so compose overrides the image
check with this script. Match an exact argv element `worker.py` so this
healthcheck process (…/worker_healthcheck.py) cannot false-positive.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                cmdline = handle.read()
        except OSError:
            continue
        parts = [part for part in cmdline.split(b"\x00") if part]
        if b"worker.py" in parts:
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
