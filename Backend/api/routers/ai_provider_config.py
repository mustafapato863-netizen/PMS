"""Admin-only management of AI provider models and encrypted API keys.

Mounted separately from the user-facing AI router so configuration stays
available while the PMS AI product switch is off. Every endpoint is strictly
Admin-only; secrets are masked on read and encrypted at rest.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from config.database import get_db, release_read_transaction
from models.ai_schemas import (
    AiProviderConfigItem,
    AiProviderConfigListResponse,
    AiProviderConfigResponse,
    AiProviderConfigUpdateRequest,
    AiProviderKeyState,
    AiProviderSwitchKeyRequest,
    AiProviderSwitchKeyResponse,
    AiProviderTestRequest,
    AiProviderTestResponse,
    AiProviderTestResult,
)
from models.models import AiProviderConfig
from services.ai import provider_config_store
from services.ai.feature_gate import require_ai_admin
from services.ai.provider_probe import probe_provider
from services.ai.secret_crypto import encrypt_secret, mask_secret
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ai/admin",
    tags=["PMS AI Provider Configuration"],
    dependencies=[Depends(require_ai_admin)],
)

ProviderName = Literal["cloudflare", "nvidia"]

_PROVIDER_LABELS: dict[str, str] = {
    "cloudflare": "Cloudflare Workers AI · Fallback chat",
    "nvidia": "NVIDIA NIM · Primary chat and feedback",
}


def _validate_provider(provider: str) -> str:
    if provider not in provider_config_store.PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown AI provider",
        )
    return provider


def _request_user_id(request: Request) -> uuid.UUID | None:
    user = getattr(request.state, "user", None)
    if not isinstance(user, dict):
        return None
    raw = str(user.get("user_id") or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _audit(
    db: Session,
    request: Request,
    provider: str,
    *,
    operation: str,
    metadata: dict[str, Any],
) -> None:
    """Write an audit row containing metadata only — never secret values."""
    try:
        record_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"ai-provider-config:{provider}"))
        AuditService.log_operation(
            db,
            table_name="ai_provider_configs",
            operation=operation,
            record_id=record_id,
            old_values=None,
            new_values={"provider": provider, **metadata},
            performed_by_user_id=_request_user_id(request),
            commit=True,
        )
    except Exception:
        logger.warning("Could not write AI provider audit entry for %s", provider, exc_info=False)


def _to_key_state(
    slot: Literal["primary", "alternate"],
    value: str,
    source: str,
) -> AiProviderKeyState:
    return AiProviderKeyState(
        slot=slot,
        configured=bool(value),
        source=source if source in ("db", "env", "none") else "none",
        masked_preview=mask_secret(value),
    )


def _to_item(config: provider_config_store.ProviderRuntimeConfig) -> AiProviderConfigItem:
    return AiProviderConfigItem(
        provider=config.provider,  # type: ignore[arg-type]
        label=_PROVIDER_LABELS.get(config.provider, config.provider),
        enabled=config.enabled,
        enabled_source=config.enabled_source,
        primary_model=config.primary_model,
        alternate_model=config.alternate_model,
        primary_model_source=config.primary_model_source,
        account_id_masked=mask_secret(config.account_id),
        alternate_account_id_masked=mask_secret(config.alternate_account_id),
        account_id_source=config.account_id_source,
        alternate_account_id_source=config.alternate_account_id_source,
        primary_key=_to_key_state("primary", config.primary_api_key, config.primary_key_source),
        alternate_key=_to_key_state(
            "alternate", config.alternate_api_key, config.alternate_key_source
        ),
        active_key_slot=config.active_key_slot,  # type: ignore[arg-type]
        auto_failover_key=config.auto_failover_key,
        daily_limit=config.daily_limit,
        updated_at=config.updated_at,
    )


def _get_or_create_row(db: Session, provider: str) -> AiProviderConfig:
    row = db.query(AiProviderConfig).filter(AiProviderConfig.provider == provider).one_or_none()
    if row is None:
        row = AiProviderConfig(provider=provider, active_key_slot="primary", auto_failover_key=True)
        db.add(row)
    return row


def _apply_slot_key(payload: AiProviderConfigUpdateRequest, row: AiProviderConfig) -> None:
    # Blank input keeps the existing key; explicit clear resets to the env default.
    if payload.clear_primary_api_key:
        row.primary_api_key_encrypted = None
    elif payload.primary_api_key is not None and payload.primary_api_key.strip():
        row.primary_api_key_encrypted = encrypt_secret(payload.primary_api_key.strip())

    if payload.clear_alternate_api_key:
        row.alternate_api_key_encrypted = None
    elif payload.alternate_api_key is not None and payload.alternate_api_key.strip():
        row.alternate_api_key_encrypted = encrypt_secret(payload.alternate_api_key.strip())


def _apply_account_ids(payload: AiProviderConfigUpdateRequest, row: AiProviderConfig) -> None:
    if payload.clear_account_id:
        row.account_id_encrypted = None
    elif payload.account_id is not None and payload.account_id.strip():
        row.account_id_encrypted = encrypt_secret(payload.account_id.strip())

    if payload.clear_alternate_account_id:
        row.alternate_account_id_encrypted = None
    elif payload.alternate_account_id is not None and payload.alternate_account_id.strip():
        row.alternate_account_id_encrypted = encrypt_secret(payload.alternate_account_id.strip())


def _slot_credentials(
    config: provider_config_store.ProviderRuntimeConfig,
    slot: str,
) -> tuple[str, str]:
    """Return (api_key, account_id) for an explicit slot."""
    if slot == "alternate":
        account_id = config.alternate_account_id or config.account_id
        return config.alternate_api_key, account_id
    return config.primary_api_key, config.account_id


@router.get("/providers", response_model=AiProviderConfigListResponse)
def list_ai_provider_configs(
    db: Session = Depends(get_db),
) -> AiProviderConfigListResponse:
    """Return all provider configurations with masked key previews."""
    providers: list[AiProviderConfigItem] = []
    for provider in provider_config_store.PROVIDERS:
        config = provider_config_store.resolve_provider_config(
            provider, db=db, use_cache=False
        )
        providers.append(_to_item(config))
    release_read_transaction(db)
    return AiProviderConfigListResponse(success=True, providers=providers)


@router.put("/providers/{provider}", response_model=AiProviderConfigResponse)
def update_ai_provider_config(
    provider: str,
    payload: AiProviderConfigUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AiProviderConfigResponse:
    """Update models, toggles, budgets, and encrypted credentials for one provider."""
    _validate_provider(provider)
    row = _get_or_create_row(db, provider)

    changed_fields: list[str] = []
    if payload.enabled is not None:
        row.enabled = bool(payload.enabled)
        changed_fields.append("enabled")
    if payload.primary_model is not None:
        row.primary_model = payload.primary_model.strip() or None
        changed_fields.append("primary_model")
    if payload.alternate_model is not None:
        row.alternate_model = payload.alternate_model.strip() or None
        changed_fields.append("alternate_model")
    if payload.daily_limit is not None:
        row.daily_limit = int(payload.daily_limit)
        changed_fields.append("daily_limit")
    if payload.auto_failover_key is not None:
        row.auto_failover_key = bool(payload.auto_failover_key)
        changed_fields.append("auto_failover_key")

    if payload.clear_primary_api_key or payload.clear_alternate_api_key:
        changed_fields.append("api_keys")
    if payload.clear_account_id or payload.clear_alternate_account_id:
        changed_fields.append("account_ids")
    if payload.primary_api_key or payload.alternate_api_key:
        changed_fields.append("api_keys")
    if payload.account_id or payload.alternate_account_id:
        changed_fields.append("account_ids")

    _apply_account_ids(payload, row)
    _apply_slot_key(payload, row)

    if payload.active_key_slot is not None:
        row.active_key_slot = payload.active_key_slot
        changed_fields.append("active_key_slot")

    row.updated_by_user_id = _request_user_id(request)
    db.flush()

    # Only an explicit slot change must prove the target slot has a credential.
    if payload.active_key_slot is not None:
        refreshed = provider_config_store.resolve_provider_config(provider, db=db, use_cache=False)
        if not refreshed.slot_has_credentials(payload.active_key_slot):
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The selected active key slot has no credentials configured",
            )

    db.commit()
    db.refresh(row)
    provider_config_store.invalidate_provider_config(provider)

    _audit(
        db,
        request,
        provider,
        operation="AI_PROVIDER_CONFIG_UPDATED",
        metadata={"fields_changed": sorted(set(changed_fields))},
    )
    saved = provider_config_store.resolve_provider_config(provider, db=db, use_cache=False)
    response = AiProviderConfigResponse(
        success=True,
        message="AI provider configuration saved",
        provider=_to_item(saved),
    )
    release_read_transaction(db)
    return response


@router.post("/providers/{provider}/switch-key", response_model=AiProviderSwitchKeyResponse)
def switch_ai_provider_key(
    provider: str,
    request: Request,
    payload: AiProviderSwitchKeyRequest | None = None,
    db: Session = Depends(get_db),
) -> AiProviderSwitchKeyResponse:
    """Switch the active credential slot with one click, without a restart."""
    _validate_provider(provider)
    row = _get_or_create_row(db, provider)

    current = provider_config_store.resolve_provider_config(provider, db=db, use_cache=False)
    target = payload.slot if payload is not None and payload.slot else (
        "alternate" if current.active_key_slot == "primary" else "primary"
    )
    if not current.slot_has_credentials(target):
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The {target} key slot has no credentials configured",
        )

    row.active_key_slot = target
    row.updated_by_user_id = _request_user_id(request)
    db.commit()
    db.refresh(row)
    provider_config_store.invalidate_provider_config(provider)

    _audit(
        db,
        request,
        provider,
        operation="AI_PROVIDER_KEY_SWITCHED",
        metadata={"slot": target},
    )
    saved = provider_config_store.resolve_provider_config(provider, db=db, use_cache=False)
    response = AiProviderSwitchKeyResponse(
        success=True,
        message=f"Active key switched to {target}",
        provider=_to_item(saved),
    )
    release_read_transaction(db)
    return response


@router.post("/providers/{provider}/test", response_model=AiProviderTestResponse)
def test_ai_provider_key(
    provider: str,
    payload: AiProviderTestRequest,
    db: Session = Depends(get_db),
) -> AiProviderTestResponse:
    """Verify a saved slot or an unsaved draft key with one tiny live call."""
    _validate_provider(provider)
    config = provider_config_store.resolve_provider_config(provider, db=db, use_cache=False)
    slot = payload.slot

    # Do not hold a database transaction open across the outbound provider call.
    release_read_transaction(db)

    saved_key, saved_account = _slot_credentials(config, slot)
    api_key = (payload.api_key or "").strip() or saved_key
    account_id = (payload.account_id or "").strip() or saved_account
    slot_model = config.alternate_model if slot == "alternate" else None
    model = (payload.model or "").strip() or slot_model or config.primary_model

    result = probe_provider(
        provider,
        api_key=api_key,
        model=model,
        account_id=account_id,
    )
    return AiProviderTestResponse(
        success=True,
        message="AI provider key test completed",
        data=AiProviderTestResult(
            ok=bool(result.get("ok")),
            latency_ms=float(result.get("latency_ms") or 0.0),
            status_code=int(result.get("status_code") or 0),
            message=str(result.get("message") or ""),
            tested_model=str(result.get("tested_model") or model),
            tested_slot=slot,
        ),
    )
