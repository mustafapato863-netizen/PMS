"""Authenticated encryption at rest for AI provider secrets.

Keys are encrypted with PyCA ``cryptography.fernet`` (AES-128-CBC + HMAC-SHA256).
The Fernet key is derived with SHA-256 from ``PMS_SECRETS_ENCRYPTION_KEY`` when
set, otherwise from ``JWT_SECRET`` using a domain-separation salt so existing
deployments work without any new environment variable.

Secrets never leave this module in plaintext except through :func:`decrypt_secret`,
which is only called by the provider runtime immediately before an outbound call.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised through the public helpers
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment,misc]

DOMAIN_SALT = "pms-ai-provider-secrets-v1"
_MASK = "\u2022\u2022\u2022\u2022"  # four bullets


def _encryption_material() -> str:
    """Return the strongest configured secret material, or an empty string."""
    explicit = (os.environ.get("PMS_SECRETS_ENCRYPTION_KEY") or "").strip()
    if explicit:
        return explicit
    # Import lazily: config.settings validates production secrets and may raise
    # in minimal test environments, in which case encryption is simply disabled.
    try:
        from config.settings import JWT_SECRET

        return str(JWT_SECRET or "").strip()
    except Exception:  # pragma: no cover - configuration error path
        return ""


def _fernet() -> "Fernet":
    if Fernet is None:  # pragma: no cover
        raise RuntimeError("cryptography is not installed; provider secret storage is unavailable")
    material = _encryption_material()
    if not material:
        raise RuntimeError("No encryption material configured for AI provider secrets")
    digest = hashlib.sha256(f"{DOMAIN_SALT}:{material}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str | None) -> str | None:
    """Encrypt a secret for at-rest storage. Blank input is stored as NULL."""
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return None
    return _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str:
    """Decrypt a stored secret. Returns an empty string when absent or unreadable."""
    if not value:
        return ""
    if Fernet is None:  # pragma: no cover
        return ""
    try:
        return _fernet().decrypt(str(value).encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError, RuntimeError):
        # Wrong key material or a legacy plaintext value: never echo the input.
        logger.warning("Stored AI provider secret could not be decrypted; treating it as unset")
        return ""


def mask_secret(value: str | None) -> str:
    """Return a short preview that identifies a key without exposing it.

    Examples: ``nvapi-••••7a2f``, ``AIza••••9x1q``, ``••••3b9e``.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("nvapi-"):
        suffix = text[-4:] if len(text) > len("nvapi-") + 4 else ""
        return f"nvapi-{_MASK}{suffix}"
    if text.startswith("AIza"):
        suffix = text[-4:] if len(text) > 8 else ""
        return f"AIza{_MASK}{suffix}"
    if len(text) >= 12:
        return f"{text[:4]}{_MASK}{text[-4:]}"
    if len(text) >= 6:
        return f"{_MASK}{text[-2:]}"
    return _MASK
