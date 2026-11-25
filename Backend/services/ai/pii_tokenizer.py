"""Reversible server-side PII pseudonymizer for LLM synthesis payloads.

Replaces employee names and employee IDs with deterministic placeholders
(e.g. ``EMP_01``, ``EMP_02``) before any external cloud LLM call and restores
exact verified names/IDs after claim validation passes.
"""
from __future__ import annotations

import re
from typing import Any


class PiiPseudonymizer:
    """Bidirectional, deterministic pseudonymizer scoped to a single AI turn."""

    def __init__(self) -> None:
        self._name_to_token: dict[str, str] = {}
        self._token_to_name: dict[str, str] = {}
        self._id_to_token: dict[str, str] = {}
        self._token_to_id: dict[str, str] = {}
        self._alias_to_token: dict[str, str] = {}

    def register_employee(
        self,
        *,
        employee_name: str | None = None,
        employee_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        name_token: str | None = None
        id_token: str | None = None

        clean_name = str(employee_name or "").strip()
        if clean_name and len(clean_name) >= 2:
            key = clean_name.casefold()
            if key not in self._name_to_token:
                idx = len(self._name_to_token) + 1
                token = f"EMP_{idx:02d}"
                self._name_to_token[key] = token
                self._token_to_name[token] = clean_name
                # Also map first+last name alias for robust prompt masking
                parts = clean_name.split()
                if len(parts) >= 2:
                    short = f"{parts[0]} {parts[-1]}".casefold()
                    self._alias_to_token.setdefault(short, token)
            name_token = self._name_to_token[key]

        clean_id = str(employee_id or "").strip()
        if clean_id and len(clean_id) >= 3:
            id_key = clean_id.casefold()
            if id_key not in self._id_to_token:
                idx = len(self._id_to_token) + 1
                token = f"ID_{idx:02d}"
                self._id_to_token[id_key] = token
                self._token_to_id[token] = clean_id
            id_token = self._id_to_token[id_key]

        return name_token, id_token

    def register_from_evidence_and_digests(
        self,
        *,
        typed_evidence: list[Any] | None = None,
        digests: list[dict[str, Any]] | None = None,
    ) -> None:
        for ev in typed_evidence or []:
            self.register_employee(
                employee_name=getattr(ev, "employee_name", None),
                employee_id=getattr(ev, "employee_id", None),
            )
            if getattr(ev, "subject_type", None) in ("person", "employee", "agent"):
                self.register_employee(employee_name=getattr(ev, "subject", None))

        def _walk(node: Any) -> None:
            if isinstance(node, dict):
                e_name = node.get("employee_name") or node.get("name") if ("employee_id" in node or "employee_name" in node) else None
                e_id = node.get("employee_id")
                if e_name or e_id:
                    self.register_employee(
                        employee_name=str(e_name) if e_name else None,
                        employee_id=str(e_id) if e_id else None,
                    )
                for val in node.values():
                    _walk(val)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        for digest in digests or []:
            _walk(digest)

    @property
    def has_mappings(self) -> bool:
        return bool(self._token_to_name or self._token_to_id)

    def tokenize_text(self, text: str) -> str:
        if not text or not self.has_mappings:
            return text
        out = text
        # Replace longer strings first so full names win over short aliases
        pairs: list[tuple[str, str]] = []
        for token, orig_name in self._token_to_name.items():
            pairs.append((orig_name, token))
        for alias_cf, token in self._alias_to_token.items():
            pairs.append((alias_cf, token))
        for token, orig_id in self._token_to_id.items():
            pairs.append((orig_id, token))
        pairs.sort(key=lambda item: len(item[0]), reverse=True)
        for raw_val, token in pairs:
            if not raw_val:
                continue
            out = re.sub(re.escape(raw_val), token, out, flags=re.IGNORECASE)
        return out

    def tokenize_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.tokenize_text(obj)
        if isinstance(obj, list):
            return [self.tokenize_obj(item) for item in obj]
        if isinstance(obj, dict):
            return {k: self.tokenize_obj(v) for k, v in obj.items()}
        return obj

    def detokenize_text(self, text: str) -> str:
        if not text or not self.has_mappings:
            return text
        out = text
        for token, orig_name in self._token_to_name.items():
            out = re.sub(rf"\[?{re.escape(token)}\]?", orig_name, out)
        for token, orig_id in self._token_to_id.items():
            out = re.sub(rf"\[?{re.escape(token)}\]?", orig_id, out)
        return out

    def has_unmasked_pii(self, text: str) -> bool:
        if not text or not self.has_mappings:
            return False
        lower = text.casefold()
        for orig_name in self._token_to_name.values():
            if len(orig_name) >= 3 and orig_name.casefold() in lower:
                return True
        for orig_id in self._token_to_id.values():
            if len(orig_id) >= 3 and orig_id.casefold() in lower:
                return True
        return False
