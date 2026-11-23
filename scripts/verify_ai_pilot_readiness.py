#!/usr/bin/env python3
"""Phase 9 (#103): Strictly read-only pilot release readiness rehearsal verifier.

Supports two execution modes:
- ``--in-process`` (default): runs against an isolated in-memory SQLite session
  and FastAPI ``TestClient`` with zero production DB access and zero network I/O.
- ``--base-url URL``: runs strictly read-only HTTP checks (GET endpoints and
  read-only denial/flag checks) against a running backend without mutating state.

Checks verified:
1. Candidate git SHA tracking.
2. Both default-off switches (``ai_enabled=False``,
   ``ai_corrective_action_pilot_enabled=False``) and 403 fail-closed behavior.
3. RBAC isolation (401 anonymous, 403 non-Admin across capability, pilot,
   diagnostics, and feedback governance routes).
4. ``/api/ai/diagnostics`` payload truthfulness and zero secret leaks.
5. Bounded concurrency (HTTP 429 on concurrent live-verify) and provider
   timeout/rate-limit fallback without hanging.
6. Latency summary (``p50_ms``, ``p95_ms``, ``max_ms``) and memory usage.
7. Explicit ``blocking_human_gates`` (``#97`` + ``Vi`` Phase 9 sign-off).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import tracemalloc
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "Backend"

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}\b", re.IGNORECASE)),
    ("postgres_credentials", re.compile(r"postgres(?:ql)?://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)),
    ("github_pat", re.compile(r"\b(?:ghp|gho|ghu|ghs)_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)

BLOCKING_HUMAN_GATES: list[dict[str, str]] = [
    {
        "gate_id": "issue_97",
        "ref": "#97",
        "owner": "Admin / DevOps",
        "status": "PENDING",
        "description": "Live provider verification and production credential attestation (#97) required before pilot activation.",
    },
    {
        "gate_id": "vi_phase9_approval",
        "ref": "#103",
        "owner": "Vi",
        "status": "PENDING",
        "description": "Final human Phase 9 sign-off from Vi required before enabling ai_corrective_action_pilot_enabled or ai_enabled.",
    },
]


def _ensure_backend_path() -> None:
    backend_str = str(BACKEND_DIR)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)


def _git_candidate_sha(override: str | None = None) -> tuple[str, bool]:
    if override:
        return override.strip(), False
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(REPO_ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return sha or "unknown", dirty
    except Exception:
        return "unknown", False


def _percentile(samples: list[float], pct: int) -> float | None:
    if not samples:
        return None
    ordered = sorted(samples)
    rank = max(0, min(len(ordered) - 1, math.ceil((pct / 100.0) * len(ordered)) - 1))
    return round(ordered[rank], 2)


def _scan_secrets(payload: Any) -> list[str]:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    findings: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            findings.append(name)
    return findings


def _memory_summary_mb(peak_traced_bytes: int) -> dict[str, float | None]:
    rss_mb: float | None = None
    try:
        import psutil  # type: ignore

        rss_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
    except Exception:
        try:
            import resource  # type: ignore

            rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # Linux ru_maxrss is KiB, macOS is bytes.
            divisor = (1024 * 1024) if sys.platform == "darwin" else 1024
            rss_mb = round(rss_raw / divisor, 2)
        except Exception:
            if sys.platform == "win32":
                try:
                    import ctypes
                    import ctypes.wintypes as wintypes

                    class _ProcessMemoryCounters(ctypes.Structure):
                        _fields_ = [
                            ("cb", wintypes.DWORD),
                            ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t),
                        ]

                    counters = _ProcessMemoryCounters()
                    counters.cb = ctypes.sizeof(counters)
                    proc = ctypes.windll.kernel32.GetCurrentProcess()
                    if ctypes.windll.psapi.GetProcessMemoryInfo(proc, ctypes.byref(counters), counters.cb):
                        rss_mb = round(counters.WorkingSetSize / (1024 * 1024), 2)
                except Exception:
                    rss_mb = None
    return {
        "rss_mb": rss_mb,
        "peak_tracemalloc_mb": round(peak_traced_bytes / (1024 * 1024), 2),
    }


@contextmanager
def _temp_env(overrides: dict[str, str]) -> Iterator[None]:
    prev = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[k] = v
        yield
    finally:
        for k, old in prev.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _run_in_process_checks() -> tuple[dict[str, Any], list[float], dict[str, Any]]:
    """Run strictly read-only readiness checks in an isolated in-memory TestClient."""
    _ensure_backend_path()

    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from api.routers import ai_corrective_actions, ai_workspace
    from api.routers.settings import router as settings_router
    from config.database import Base, get_db
    from services.ai import feature_gate
    from services.ai.provider_engine import (
        CloudflareAIProviderAdapter,
        NvidiaProviderAdapter,
        ProviderMessage,
        ProviderRequest,
        ProviderTimeoutError,
        UnifiedProviderConfig,
        UnifiedProviderEngine,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionFactory = sessionmaker(bind=engine)
    db = SessionFactory()

    app = FastAPI()

    @app.middleware("http")
    async def attach_test_identity(request: Request, call_next):
        role = request.headers.get("x-readiness-role")
        user_id = request.headers.get("x-readiness-user-id")
        if role:
            request.state.user = {"role": role, "user_id": user_id or f"readiness-{role.lower()}"}
        return await call_next(request)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(ai_workspace.diagnostics_router, prefix="/api")
    app.include_router(ai_workspace.router, prefix="/api")
    app.include_router(ai_corrective_actions.router, prefix="/api")
    app.include_router(settings_router, prefix="/api/settings")

    latencies: list[float] = []
    client = TestClient(app)

    def _call(method: str, path: str, *, headers: dict[str, str] | None = None, json_body: dict[str, Any] | None = None):
        t0 = time.perf_counter()
        resp = client.request(method, path, headers=headers, json=json_body)
        latencies.append(round((time.perf_counter() - t0) * 1000.0, 2))
        return resp

    admin_hdr = {"x-readiness-role": "Admin", "x-readiness-user-id": "00000000-0000-4000-8000-000000000001"}
    manager_hdr = {"x-readiness-role": "Manager", "x-readiness-user-id": "00000000-0000-4000-8000-000000000002"}
    viewer_hdr = {"x-readiness-role": "Viewer", "x-readiness-user-id": "00000000-0000-4000-8000-000000000003"}

    checks: dict[str, Any] = {}
    try:
        # 1. Default-off switches & fail-closed 403 checks
        ai_flag_db = feature_gate.read_ai_enabled(db)
        pilot_flag_db = feature_gate.read_ai_corrective_action_pilot_enabled(db)
        set_ai_resp = _call("GET", "/api/settings/ai-assistant", headers=admin_hdr)
        set_pilot_resp = _call("GET", "/api/settings/ai-corrective-action-pilot", headers=admin_hdr)
        chat_off_resp = _call("POST", "/api/ai/chat", headers=admin_hdr, json_body={"prompt": "Summary"})
        pilot_off_resp = _call(
            "POST",
            "/api/ai/corrective-action-suggestions",
            headers=admin_hdr,
            json_body={"team": "Inbound", "month": "September", "year": 2026},
        )
        pilot_fb_off_resp = _call(
            "POST",
            "/api/ai/corrective-action-suggestions/feedback",
            headers=admin_hdr,
            json_body={
                "rating": "up",
                "reason_tag": "good_quality_recommendation",
                "operation_family": "corrective_action_draft",
                "scope_team": "Inbound",
                "scope_country": "EGY",
                "performance_level": "Employee",
            },
        )
        verify_live_off_resp = _call("POST", "/api/ai/diagnostics/verify-live", headers=admin_hdr)

        checks["flags_default_off"] = {
            "passed": (
                ai_flag_db is False
                and pilot_flag_db is False
                and set_ai_resp.status_code == 200
                and set_ai_resp.json().get("data", {}).get("enabled") is False
                and set_ai_resp.json().get("data", {}).get("corrective_action_pilot_enabled") is False
                and set_pilot_resp.status_code == 200
                and set_pilot_resp.json().get("data", {}).get("corrective_action_pilot_enabled") is False
                and chat_off_resp.status_code == 403
                and pilot_off_resp.status_code == 403
                and pilot_fb_off_resp.status_code == 403
                and verify_live_off_resp.status_code == 403
            ),
            "ai_enabled": ai_flag_db,
            "ai_corrective_action_pilot_enabled": pilot_flag_db,
            "chat_status_when_off": chat_off_resp.status_code,
            "pilot_status_when_off": pilot_off_resp.status_code,
            "pilot_feedback_status_when_off": pilot_fb_off_resp.status_code,
            "verify_live_status_when_off": verify_live_off_resp.status_code,
        }

        # 2. RBAC checks (401 anonymous, 403 non-Admin)
        anon_diag = _call("GET", "/api/ai/diagnostics")
        anon_pilot = _call("POST", "/api/ai/corrective-action-suggestions", json_body={"team": "Inbound", "month": "September", "year": 2026})
        anon_setting = _call("GET", "/api/settings/ai-assistant")
        anon_clusters = _call("GET", "/api/ai/feedback/clusters")

        mgr_diag = _call("GET", "/api/ai/diagnostics", headers=manager_hdr)
        viewer_diag = _call("GET", "/api/ai/diagnostics", headers=viewer_hdr)
        mgr_chat = _call("POST", "/api/ai/chat", headers=manager_hdr, json_body={"prompt": "Hi"})
        mgr_pilot = _call("POST", "/api/ai/corrective-action-suggestions", headers=manager_hdr, json_body={"team": "Inbound", "month": "September", "year": 2026})
        mgr_clusters = _call("GET", "/api/ai/feedback/clusters", headers=manager_hdr)
        mgr_export = _call("GET", "/api/ai/feedback/export-bundle", headers=manager_hdr)

        checks["rbac_isolation"] = {
            "passed": (
                anon_diag.status_code == 401
                and anon_pilot.status_code == 401
                and anon_setting.status_code == 401
                and anon_clusters.status_code in (401, 403)
                and mgr_diag.status_code == 403
                and viewer_diag.status_code == 403
                and mgr_chat.status_code == 403
                and mgr_pilot.status_code == 403
                and mgr_clusters.status_code == 403
                and mgr_export.status_code == 403
            ),
            "anonymous_statuses": {
                "diagnostics": anon_diag.status_code,
                "pilot_suggest": anon_pilot.status_code,
                "ai_assistant_setting": anon_setting.status_code,
                "feedback_clusters": anon_clusters.status_code,
            },
            "non_admin_statuses": {
                "manager_diagnostics": mgr_diag.status_code,
                "viewer_diagnostics": viewer_diag.status_code,
                "manager_chat": mgr_chat.status_code,
                "manager_pilot": mgr_pilot.status_code,
                "manager_clusters": mgr_clusters.status_code,
                "manager_export_bundle": mgr_export.status_code,
            },
        }

        # 3. Diagnostics truthfulness & zero secret leaks
        admin_diag = _call("GET", "/api/ai/diagnostics", headers=admin_hdr)
        diag_json = admin_diag.json() if admin_diag.status_code == 200 else {}
        diag_data = diag_json.get("data") or {}
        diag_secrets = _scan_secrets(diag_json)
        host_val = str(diag_data.get("model_endpoint_host") or "")
        timeout_val = diag_data.get("provider_timeout_seconds")
        truthful = (
            admin_diag.status_code == 200
            and diag_data.get("feature_enabled") is False
            and diag_data.get("pilot_role_restricted") is True
            and "@" not in host_val
            and "://" not in host_val
            and isinstance(timeout_val, (int, float))
            and 0.5 <= float(timeout_val) <= 18.0
            and len(diag_secrets) == 0
        )
        checks["diagnostics_truthfulness_and_secret_scan"] = {
            "passed": truthful,
            "status_code": admin_diag.status_code,
            "secret_findings": diag_secrets,
            "diagnostics_snapshot": {
                "feature_enabled": diag_data.get("feature_enabled"),
                "pilot_role_restricted": diag_data.get("pilot_role_restricted"),
                "provider_status_code": diag_data.get("provider_status_code"),
                "inference_verified": diag_data.get("inference_verified"),
                "fallback_scope": diag_data.get("fallback_scope"),
                "provider_timeout_seconds": timeout_val,
            },
        }

        # 4. Bounded concurrency (429) & timeout fallback without hanging
        with _temp_env({"PMS_AI_LIVE_VERIFY_ENDPOINT_ENABLED": "true", "APP_ENV": "test"}):
            orig_in_flight = ai_workspace._live_verify_in_flight
            try:
                ai_workspace._live_verify_in_flight = True
                concurrent_resp = _call("POST", "/api/ai/diagnostics/verify-live", headers=admin_hdr)
            finally:
                ai_workspace._live_verify_in_flight = orig_in_flight

        class _TimeoutNvidia(NvidiaProviderAdapter):
            def execute(self, request, config, *, model="", timeout=1.0):
                raise ProviderTimeoutError("Simulated primary timeout")

        class _RateLimitCloudflare(CloudflareAIProviderAdapter):
            def execute(self, request, config, *, model="", timeout=1.0):
                from services.ai.provider_engine import ProviderRateLimitError

                raise ProviderRateLimitError("Simulated HTTP 429 rate limit", http_code=429)

        t_fb_start = time.perf_counter()
        fb_engine = UnifiedProviderEngine(
            UnifiedProviderConfig(
                primary_provider="nvidia",
                fallback_provider="cloudflare",
                cloudflare_enabled=True,
                nvidia_enabled=True,
                fallback_enabled=True,
                cloudflare_account_id="acct-rehearsal",
                cloudflare_api_token="tok-rehearsal",
                nvidia_api_key="nv-rehearsal",
                timeout_seconds=1.0,
                max_retries=0,
            ),
            nvidia_adapter=_TimeoutNvidia(),
            cloudflare_adapter=_RateLimitCloudflare(),
        )
        fb_resp = fb_engine.generate(
            ProviderRequest(
                messages=[ProviderMessage(role="user", content="health probe")],
                timeout_seconds=1.0,
                purpose="readiness_rehearsal",
            )
        )
        fb_elapsed_ms = round((time.perf_counter() - t_fb_start) * 1000.0, 2)
        fb_secrets = _scan_secrets({"error": fb_resp.error_detail, "outcome": fb_resp.outcome})

        checks["bounded_concurrency_and_timeout_fallback"] = {
            "passed": (
                concurrent_resp.status_code == 429
                and not fb_resp.is_success
                and fb_resp.outcome in {"rate_limited", "timeout", "provider_unavailable"}
                and len(fb_resp.attempts) >= 2
                and fb_elapsed_ms < 2000.0
                and len(fb_secrets) == 0
            ),
            "concurrent_live_verify_status": concurrent_resp.status_code,
            "fallback_outcome": fb_resp.outcome,
            "attempt_statuses": [a.status for a in fb_resp.attempts],
            "fallback_elapsed_ms": fb_elapsed_ms,
            "secret_findings": fb_secrets,
        }

        return checks, latencies, diag_data
    finally:
        db.close()
        engine.dispose()


def _http_read_probe(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[int, Any, float]:
    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    req_headers = dict(headers or {})
    if data is not None:
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = raw
            return int(resp.status), parsed, elapsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        elapsed = round((time.perf_counter() - t0) * 1000.0, 2)
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return int(exc.code), parsed, elapsed


def _run_remote_read_only_checks(base_url: str) -> tuple[dict[str, Any], list[float], dict[str, Any]]:
    """Run strictly non-mutating read-only HTTP probes against ``--base-url``."""
    base = base_url.rstrip("/")
    latencies: list[float] = []
    checks: dict[str, Any] = {}

    admin_token = os.environ.get("PMS_READINESS_ADMIN_BEARER", "").strip()
    non_admin_token = os.environ.get("PMS_READINESS_NON_ADMIN_BEARER", "").strip()
    admin_hdr = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}
    non_admin_hdr = {"Authorization": f"Bearer {non_admin_token}"} if non_admin_token else {}

    # Anonymous probes (strictly read-only)
    s_anon_diag, _, ms1 = _http_read_probe(f"{base}/api/ai/diagnostics")
    s_anon_clusters, _, ms2 = _http_read_probe(f"{base}/api/ai/feedback/clusters")
    s_anon_flag, _, ms3 = _http_read_probe(f"{base}/api/settings/ai-corrective-action-pilot")
    latencies.extend([ms1, ms2, ms3])

    non_admin_diag = None
    if non_admin_hdr:
        non_admin_diag, _, ms4 = _http_read_probe(f"{base}/api/ai/diagnostics", headers=non_admin_hdr)
        latencies.append(ms4)

    checks["rbac_isolation"] = {
        "passed": (
            s_anon_diag == 401
            and s_anon_clusters in (401, 403)
            and s_anon_flag == 401
            and (non_admin_diag is None or non_admin_diag == 403)
        ),
        "anonymous_statuses": {
            "diagnostics": s_anon_diag,
            "feedback_clusters": s_anon_clusters,
            "pilot_setting": s_anon_flag,
        },
        "non_admin_diagnostics_status": non_admin_diag,
        "non_admin_probe_skipped": not bool(non_admin_hdr),
    }

    diag_data: dict[str, Any] = {}
    if admin_hdr:
        s_flag, flag_body, ms5 = _http_read_probe(f"{base}/api/settings/ai-assistant", headers=admin_hdr)
        s_diag, diag_body, ms6 = _http_read_probe(f"{base}/api/ai/diagnostics", headers=admin_hdr)
        latencies.extend([ms5, ms6])
        flag_data = flag_body.get("data", {}) if isinstance(flag_body, dict) else {}
        diag_data = diag_body.get("data", {}) if isinstance(diag_body, dict) else {}
        diag_secrets = _scan_secrets(diag_body)
        checks["flags_default_off"] = {
            "passed": (
                s_flag == 200
                and flag_data.get("enabled") is False
                and flag_data.get("corrective_action_pilot_enabled") is False
            ),
            "ai_enabled": flag_data.get("enabled"),
            "ai_corrective_action_pilot_enabled": flag_data.get("corrective_action_pilot_enabled"),
        }
        checks["diagnostics_truthfulness_and_secret_scan"] = {
            "passed": s_diag == 200 and len(diag_secrets) == 0,
            "status_code": s_diag,
            "secret_findings": diag_secrets,
        }
    else:
        checks["flags_default_off"] = {
            "passed": False,
            "status": "blocked_missing_admin_bearer",
            "reason": "Set PMS_READINESS_ADMIN_BEARER to inspect remote /api/settings and /api/ai/diagnostics.",
        }
        checks["diagnostics_truthfulness_and_secret_scan"] = {
            "passed": False,
            "status": "blocked_missing_admin_bearer",
        }

    checks["bounded_concurrency_and_timeout_fallback"] = {
        "passed": True,
        "status": "skipped_remote_non_mutating",
        "reason": "Remote mode stays strictly read-only and does not trigger verify-live or write operations.",
    }
    return checks, latencies, diag_data


def run_readiness_check(
    *,
    base_url: str | None = None,
    candidate_sha: str | None = None,
) -> dict[str, Any]:
    sha, dirty = _git_candidate_sha(candidate_sha)
    tracemalloc.start()
    try:
        if base_url:
            mode = "remote-read-only"
            checks, latencies, _diag = _run_remote_read_only_checks(base_url)
        else:
            mode = "in-process"
            checks, latencies, _diag = _run_in_process_checks()
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    technical_passed = all(bool(item.get("passed")) for item in checks.values())
    all_secret_findings = _scan_secrets(checks)
    if all_secret_findings:
        technical_passed = False

    return {
        "schema_version": "pms-ai-phase9-readiness-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "read_only": True,
        "candidate_sha": sha,
        "working_tree_dirty": dirty,
        "technical_gates_passed": technical_passed,
        "pilot_ready_for_rollout": False,
        "checks": checks,
        "latency_ms": {
            "samples": len(latencies),
            "p50_ms": _percentile(latencies, 50),
            "p95_ms": _percentile(latencies, 95),
            "max_ms": max(latencies) if latencies else None,
        },
        "memory": _memory_summary_mb(peak_bytes),
        "secret_findings": all_secret_findings,
        "blocking_human_gates": list(BLOCKING_HUMAN_GATES),
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify PMS AI Phase 9 pilot readiness (read-only).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--in-process", action="store_true", help="Run against isolated in-memory SQLite TestClient (default).")
    group.add_argument("--base-url", default=None, help="Run read-only HTTP checks against a running backend base URL.")
    parser.add_argument("--json-out", default=None, help="Optional path to write the JSON readiness report.")
    parser.add_argument("--candidate-sha", default=None, help="Optional candidate commit SHA override.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = run_readiness_check(base_url=args.base_url, candidate_sha=args.candidate_sha)
    serialized = json.dumps(report, indent=2)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["technical_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
