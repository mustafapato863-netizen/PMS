"""Security hardening utilities for AI assistant.

Provides XML tag breakout prevention and evidence fencing.
"""

from __future__ import annotations


def fence_untrusted_evidence(text: str) -> str:
    """Escape XML-sensitive chars before wrapping in <untrusted_evidence>.

    Prevents tag breakout attacks where malicious data in evidence
    could escape the XML fencing.
    """
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace("`", "&#96;")
    return f"<untrusted_evidence>{text}</untrusted_evidence>"


def redact_nested_payload(payload: dict, keys_to_redact: set[str] | None = None) -> dict:
    """Redact sensitive keys from a nested payload dict."""
    if keys_to_redact is None:
        keys_to_redact = {
            "employee_code",
            "employee_pk",
            "username",
            "password",
            "password_hash",
            "email",
            "token",
            "secret",
        }
    result = {}
    for key, value in payload.items():
        if key in keys_to_redact:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = redact_nested_payload(value, keys_to_redact)
        elif isinstance(value, list):
            result[key] = [
                redact_nested_payload(item, keys_to_redact) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result
