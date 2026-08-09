import os
import json
import time
import threading
from typing import Any, List, Optional
from config.settings import APP_ENV, DATA_DIR
from models.schemas import (
    Employee, PerformanceRecord, KPIWeight, Target, UploadRecord, ManagerNote, CorrectiveAction, TeamAction, UserRecord
)
from repositories.base import (
    EmployeeRepository, PerformanceRepository, KPIWeightsRepository, TargetsRepository,
    UploadsRepository, ManagerNotesRepository, CorrectiveActionsRepository
)

# ── in-memory cache for JSON file data ──
_cache: dict[str, tuple[list | dict, float]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 5 minutes — invalidated early on writes

_PERFORMANCE_SCORE_KEYS = ("PerformanceScore", "PerformanceScore%", "Performance_Score")


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_percentage_score(value: Any) -> float | None:
    score = _coerce_float(value)
    if score is None:
        return None
    if 0.0 < score <= 1.0:
        score *= 100.0
    return max(0.0, min(score, 100.0))


def _sanitize_performance_record_item(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(item)
    evaluation = sanitized.get("evaluation")
    if isinstance(evaluation, dict):
        normalized_score = _normalize_percentage_score(evaluation.get("score"))
        if normalized_score is not None:
            evaluation = dict(evaluation)
            evaluation["score"] = round(normalized_score, 2)
            sanitized["evaluation"] = evaluation
    raw_data = sanitized.get("raw_data")
    if isinstance(raw_data, dict):
        raw_data = dict(raw_data)
        for key in _PERFORMANCE_SCORE_KEYS:
            normalized_raw_score = _normalize_percentage_score(raw_data.get(key))
            if normalized_raw_score is not None:
                raw_data[key] = round(normalized_raw_score, 2)
        sanitized["raw_data"] = raw_data
    return sanitized


def _sanitize_loaded_json(filename: str, data: list | dict) -> list | dict:
    if filename != "performance_records.json" or not isinstance(data, list):
        return data
    return [_sanitize_performance_record_item(item) if isinstance(item, dict) else item for item in data]


def _prepare_json_for_save(filename: str, data: list | dict) -> list | dict:
    if filename != "performance_records.json":
        return data
    if isinstance(data, list):
        return [_sanitize_performance_record_item(item) if isinstance(item, dict) else item for item in data]
    if isinstance(data, dict):
        return _sanitize_performance_record_item(data)
    return data


def _load_json(filename: str, default_val: list | dict) -> list | dict:
    now = time.time()
    cache_key = f"json:{filename}"

    with _cache_lock:
        entry = _cache.get(cache_key)
        if entry is not None and now < entry[1]:
            return entry[0]

    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        with _cache_lock:
            _cache[cache_key] = (default_val, now + _CACHE_TTL)
        return default_val

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = _sanitize_loaded_json(filename, json.load(f))
        with _cache_lock:
            _cache[cache_key] = (data, now + _CACHE_TTL)
        return data
    except Exception:
        with _cache_lock:
            _cache[cache_key] = (default_val, now + _CACHE_TTL)
        return default_val

def _save_json(filename: str, data: list | dict):
    path = os.path.join(DATA_DIR, filename)
    data = _prepare_json_for_save(filename, data)
    temp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except OSError as e:
        import logging
        logging.getLogger(__name__).warning(f"Skipping JSON save for {filename} due to filesystem restriction: {e}")
    # Invalidate cache so next read picks up the new data
    with _cache_lock:
        _cache.pop(f"json:{filename}", None)


class JSONEmployeeRepository(EmployeeRepository):
    def __init__(self):
        self.filename = "employees.json"

    def get_by_id(self, employee_id: str) -> Optional[Employee]:
        data = _load_json(self.filename, [])
        for item in data:
            if str(item.get("id")) == str(employee_id):
                return Employee(**item)
        return None

    def get_all(self) -> List[Employee]:
        data = _load_json(self.filename, [])
        return [Employee(**item) for item in data]

    def save(self, employee: Employee) -> Employee:
        data = _load_json(self.filename, [])
        # Remove existing if exists
        data = [item for item in data if str(item.get("id")) != str(employee.id)]
        data.append(employee.model_dump())
        _save_json(self.filename, data)
        return employee

    def save_all(self, employees: List[Employee]) -> List[Employee]:
        data = _load_json(self.filename, [])
        ids_to_save = {str(e.id) for e in employees}
        data = [item for item in data if str(item.get("id")) not in ids_to_save]
        for e in employees:
            data.append(e.model_dump())
        _save_json(self.filename, data)
        return employees

    def replace_all(self, employees: List[Employee]) -> None:
        _save_json(self.filename, [employee.model_dump() for employee in employees])


class JSONPerformanceRepository(PerformanceRepository):
    def __init__(self):
        self.filename = "performance_records.json"

    def _all_records(self) -> List[PerformanceRecord]:
        data = _load_json(self.filename, [])
        return [PerformanceRecord(**item) for item in data]

    def get_by_id(self, record_id: str) -> Optional[PerformanceRecord]:
        return next((record for record in self._all_records() if record.id == record_id), None)

    def get_by_employee_and_month(
        self,
        employee_id: str,
        month: str,
        year: int | None = None,
    ) -> Optional[PerformanceRecord]:
        return next(
            (
                record
                for record in self._all_records()
                if str(record.employee_id) == str(employee_id) and record.month == month
                and (year is None or record.year == year)
            ),
            None,
        )

    def get_all(self) -> List[PerformanceRecord]:
        return self._all_records()

    def get_filtered(
        self,
        team: str | None = None,
        month: str | None = None,
        employee_id: str | None = None,
        grade: str | None = None,
        status: str | None = None,
        performance_level: str | None = None,
        year: int | None = None,
        position: str | None = None,
        region: str | None = None,
    ) -> List[PerformanceRecord]:
        records = self.get_all()
        if team:
            records = [r for r in records if r.team == team]
        if month:
            records = [r for r in records if r.month == month]
        if employee_id:
            records = [r for r in records if str(r.employee_id) == str(employee_id)]
        if grade:
            records = [r for r in records if getattr(r.evaluation, "grade", None) == grade]
        if status:
            status_val = status.lower()
            def resolved_status(record: PerformanceRecord) -> str:
                if isinstance(record.status, str) and record.status:
                    return record.status.lower()
                if record.evaluation.grade == "A":
                    return "exceeds"
                if record.evaluation.grade in {"B", "C"}:
                    return "meets"
                return "below"
            records = [record for record in records if resolved_status(record) == status_val]
        if performance_level:
            records = [r for r in records if r.performance_level == performance_level]
        if year is not None:
            records = [r for r in records if r.year == year]
        if position:
            records = [r for r in records if (r.position or "").casefold() == position.casefold()]
        if region:
            records = [r for r in records if (r.region or "").casefold() == region.casefold()]
        return records

    def get_filtered_by_keys(self, keys: set[tuple[str, str, str, int | None]]) -> List[PerformanceRecord]:
        if not keys:
            return []
        records = self.get_all()
        return [
            record
            for record in records
            if (str(record.employee_id), str(record.team), str(record.month), record.year) in keys
        ]

    def save(self, record: PerformanceRecord) -> PerformanceRecord:
        data = _load_json(self.filename, [])
        data = [item for item in data if item.get("id") != record.id]
        data.append(record.model_dump())
        _save_json(self.filename, data)
        return record

    def save_all(self, records: List[PerformanceRecord]) -> List[PerformanceRecord]:
        data = _load_json(self.filename, [])
        ids_to_save = {r.id for r in records}
        period_keys = {
            (str(r.employee_id), r.month, r.year)
            for r in records
        }
        data = [
            item for item in data
            if item.get("id") not in ids_to_save
            and (str(item.get("employee_id")), item.get("month"), item.get("year")) not in period_keys
        ]
        for r in records:
            data.append(r.model_dump())
        _save_json(self.filename, data)
        return records

    def replace_all(self, records: List[PerformanceRecord]) -> None:
        _save_json(self.filename, [record.model_dump() for record in records])

    def delete_by_upload_id(self, upload_id: str) -> List[str]:
        data = _load_json(self.filename, [])
        affected_employee_ids = []
        new_data = []
        for item in data:
            if item.get("upload_id") == upload_id:
                emp_id = item.get("employee_id")
                if emp_id:
                    affected_employee_ids.append(str(emp_id))
            else:
                new_data.append(item)
        _save_json(self.filename, new_data)
        return list(set(affected_employee_ids))


class JSONKPIWeightsRepository(KPIWeightsRepository):
    def __init__(self):
        self.filename = "kpi_weights.json"

    def get_by_team(self, team: str) -> Optional[KPIWeight]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("team") == team:
                return KPIWeight(**item)
        return None

    def get_all(self) -> List[KPIWeight]:
        data = _load_json(self.filename, [])
        return [KPIWeight(**item) for item in data]

    def save(self, weight: KPIWeight) -> KPIWeight:
        data = _load_json(self.filename, [])
        data = [item for item in data if item.get("team") != weight.team]
        data.append(weight.model_dump())
        _save_json(self.filename, data)
        return weight


class JSONTargetsRepository(TargetsRepository):
    def __init__(self):
        self.filename = "targets.json"

    def get_by_team(self, team: str) -> Optional[Target]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("team") == team:
                return Target(**item)
        return None

    def get_all(self) -> List[Target]:
        data = _load_json(self.filename, [])
        return [Target(**item) for item in data]

    def save(self, target: Target) -> Target:
        data = _load_json(self.filename, [])
        data = [item for item in data if item.get("team") != target.team]
        data.append(target.model_dump())
        _save_json(self.filename, data)
        return target


class JSONUploadsRepository(UploadsRepository):
    def __init__(self):
        self.filename = "uploads.json"

    def get_all(self) -> List[UploadRecord]:
        data = _load_json(self.filename, [])
        return [UploadRecord(**item) for item in data]

    def save(self, upload: UploadRecord) -> UploadRecord:
        data = _load_json(self.filename, [])
        data.append(upload.model_dump())
        _save_json(self.filename, data)
        return upload

    def delete_all(self) -> None:
        _save_json(self.filename, [])

    def delete_by_id(self, upload_id: str) -> bool:
        data = _load_json(self.filename, [])
        initial_len = len(data)
        data = [item for item in data if item.get("id") != upload_id]
        _save_json(self.filename, data)
        return len(data) < initial_len

    def replace_all(self, uploads: List[UploadRecord]) -> None:
        _save_json(self.filename, [upload.model_dump() for upload in uploads])


class JSONManagerNotesRepository(ManagerNotesRepository):
    def __init__(self):
        self.filename = "manager_notes.json"

    def get_note(self, employee_id: str, month: str) -> Optional[ManagerNote]:
        data = _load_json(self.filename, [])
        for item in data:
            if str(item.get("employee_id")) == str(employee_id) and item.get("month") == month:
                return ManagerNote(**item)
        return None

    def get_all_notes(self) -> List[ManagerNote]:
        data = _load_json(self.filename, [])
        return [ManagerNote(**item) for item in data]

    def save(self, note: ManagerNote) -> ManagerNote:
        data = _load_json(self.filename, [])
        data = [item for item in data if not (str(item.get("employee_id")) == str(note.employee_id) and item.get("month") == note.month)]
        data.append(note.model_dump())
        _save_json(self.filename, data)
        return note


class JSONCorrectiveActionsRepository(CorrectiveActionsRepository):
    def __init__(self):
        self.filename = "corrective_actions.json"

    def get_latest_by_employee_and_month(self, employee_id: str, month: str) -> Optional[CorrectiveAction]:
        history = self.get_history(employee_id)
        latest = None
        for action in history:
            if action.month == month:
                latest = action
        return latest

    def get_history(self, employee_id: Optional[str] = None) -> List[CorrectiveAction]:
        data = _load_json(self.filename, [])
        actions = []
        updated_any = False
        for item in data:
            if not item.get("id"):
                ts = item.get("timestamp", "default")
                item["id"] = f"{item.get('employee_id')}_{item.get('month')}_{ts}"
                updated_any = True
            actions.append(CorrectiveAction(**item))
        
        if updated_any:
            _save_json(self.filename, data)

        if employee_id:
            actions = [a for a in actions if str(a.employee_id) == str(employee_id)]
        return actions

    def save(self, action: CorrectiveAction) -> CorrectiveAction:
        data = _load_json(self.filename, [])
        if not action.id:
            ts = action.timestamp or "default"
            action.id = f"{action.employee_id}_{action.month}_{ts}"
            
        found = False
        for i, item in enumerate(data):
            curr_id = item.get("id")
            if not curr_id:
                ts = item.get("timestamp", "default")
                curr_id = f"{item.get('employee_id')}_{item.get('month')}_{ts}"
            if curr_id == action.id:
                data[i] = action.model_dump()
                found = True
                break
        if not found:
            data.append(action.model_dump())
            
        _save_json(self.filename, data)
        return action

    def delete(self, action_id: str) -> bool:
        data = _load_json(self.filename, [])
        initial_len = len(data)
        new_data = []
        for item in data:
            curr_id = item.get("id")
            if not curr_id:
                ts = item.get("timestamp", "default")
                curr_id = f"{item.get('employee_id')}_{item.get('month')}_{ts}"
            if curr_id != action_id:
                new_data.append(item)
        _save_json(self.filename, new_data)
        return len(new_data) < initial_len


class JSONTeamActionsRepository:
    def __init__(self):
        self.filename = "team_actions.json"

    def get_action(self, team_id: str, month: str, year: int | None = None) -> Optional[TeamAction]:
        data = _load_json(self.filename, [])
        if year is not None:
            for item in data:
                if item.get("team_id") == team_id and item.get("month") == month and item.get("year") == year:
                    return TeamAction(**item)
            # Compatibility-only fallback for records written before year-aware keys.
            for item in data:
                if item.get("team_id") == team_id and item.get("month") == month and item.get("year") is None:
                    return TeamAction(**item)
            return None
        for item in data:
            if item.get("team_id") == team_id and item.get("month") == month:
                return TeamAction(**item)
        return None

    def save(self, action: TeamAction) -> TeamAction:
        data = _load_json(self.filename, [])
        action.id = f"{action.team_id}_{action.year}_{action.month}" if action.year is not None else f"{action.team_id}_{action.month}"
        data = [item for item in data if item.get("id") != action.id]
        data.append(action.model_dump())
        _save_json(self.filename, data)
        return action

class JSONUserRepository:
    def __init__(self):
        self.filename = "users.json"

    def get_all(self) -> List[UserRecord]:
        data = _load_json(self.filename, [])
        return [UserRecord(**item) for item in data]

    def get_by_id(self, user_id: str) -> Optional[UserRecord]:
        data = _load_json(self.filename, [])
        for item in data:
            if item.get("id") == user_id:
                return UserRecord(**item)
        return None

    def save(self, user: UserRecord) -> UserRecord:
        data = _load_json(self.filename, [])
        # Remove existing if exists
        data = [item for item in data if item.get("id") != user.id and item.get("username").lower() != user.username.lower()]
        data.append(user.model_dump())
        _save_json(self.filename, data)
        return user

    def update(self, user_id: str, updates: dict) -> Optional[UserRecord]:
        data = _load_json(self.filename, [])
        updated = None
        new_data = []
        for item in data:
            if item.get("id") == user_id:
                item.update({k: v for k, v in updates.items() if v is not None})
                updated = UserRecord(**item)
                new_data.append(updated.model_dump())
            else:
                new_data.append(item)
        if updated is None:
            return None
        _save_json(self.filename, new_data)
        return updated

    def delete(self, user_id: str) -> bool:
        data = _load_json(self.filename, [])
        initial_len = len(data)
        data = [item for item in data if item.get("id") != user_id]
        _save_json(self.filename, data)
        return len(data) < initial_len

    def toggle_active(self, user_id: str, is_active: bool) -> bool:
        updated = self.update(user_id, {"is_active": is_active})
        return updated is not None
