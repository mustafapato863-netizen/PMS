from abc import ABC, abstractmethod
from typing import List, Optional, Any
from models.schemas import (
    Employee, PerformanceRecord, KPIWeight, Target, UploadRecord, ManagerNote, CorrectiveAction
)

class EmployeeRepository(ABC):
    @abstractmethod
    def get_by_id(self, employee_id: str) -> Optional[Employee]:
        pass

    @abstractmethod
    def get_all(self) -> List[Employee]:
        pass

    @abstractmethod
    def save(self, employee: Employee) -> Employee:
        pass

    @abstractmethod
    def save_all(self, employees: List[Employee]) -> List[Employee]:
        pass


class PerformanceRepository(ABC):
    @abstractmethod
    def get_by_id(self, record_id: str) -> Optional[PerformanceRecord]:
        pass

    @abstractmethod
    def get_by_employee_and_month(self, employee_id: str, month: str) -> Optional[PerformanceRecord]:
        pass

    @abstractmethod
    def get_all(self) -> List[PerformanceRecord]:
        pass

    @abstractmethod
    def save(self, record: PerformanceRecord) -> PerformanceRecord:
        pass

    @abstractmethod
    def save_all(self, records: List[PerformanceRecord]) -> List[PerformanceRecord]:
        pass

    @abstractmethod
    def delete_by_upload_id(self, upload_id: str) -> List[str]:
        pass


class KPIWeightsRepository(ABC):
    @abstractmethod
    def get_by_team(self, team: str) -> Optional[KPIWeight]:
        pass

    @abstractmethod
    def get_all(self) -> List[KPIWeight]:
        pass

    @abstractmethod
    def save(self, weight: KPIWeight) -> KPIWeight:
        pass


class TargetsRepository(ABC):
    @abstractmethod
    def get_by_team(self, team: str) -> Optional[Target]:
        pass

    @abstractmethod
    def get_all(self) -> List[Target]:
        pass

    @abstractmethod
    def save(self, target: Target) -> Target:
        pass


class UploadsRepository(ABC):
    @abstractmethod
    def get_all(self) -> List[UploadRecord]:
        pass

    @abstractmethod
    def save(self, upload: UploadRecord) -> UploadRecord:
        pass

    @abstractmethod
    def delete_all(self) -> None:
        pass

    @abstractmethod
    def delete_by_id(self, upload_id: str) -> bool:
        pass


class ManagerNotesRepository(ABC):
    @abstractmethod
    def get_note(self, employee_id: str, month: str) -> Optional[ManagerNote]:
        pass

    @abstractmethod
    def get_all_notes(self) -> List[ManagerNote]:
        pass

    @abstractmethod
    def save(self, note: ManagerNote) -> ManagerNote:
        pass


class CorrectiveActionsRepository(ABC):
    @abstractmethod
    def get_latest_by_employee_and_month(self, employee_id: str, month: str) -> Optional[CorrectiveAction]:
        pass

    @abstractmethod
    def get_history(self, employee_id: Optional[str] = None) -> List[CorrectiveAction]:
        pass

    @abstractmethod
    def save(self, action: CorrectiveAction) -> CorrectiveAction:
        pass

    @abstractmethod
    def delete(self, action_id: str) -> bool:
        pass
