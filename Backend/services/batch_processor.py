"""Batch Processor Service
Handles high-volume transaction batching for performance records and configuration weights.
"""

import logging
import uuid
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from models.models import PerformanceRecord, KPIValue, Team, Employee, TeamKPIConfig
from utils.performance_levels import normalize_performance_level
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles high-volume chunked database writes with transactional integrity"""

    @staticmethod
    def batch_insert_performance_records(
        db: Session,
        records_data: List[Dict[str, Any]],
        performed_by_user_id: str = None
    ) -> Dict[str, Any]:
        """
        Validates all records up-front. If clean, inserts them in chunks of 1,000 using
        nested transactions.
        
        Args:
            db: Database session
            records_data: List of performance records to insert
            performed_by_user_id: User ID performing action
            
        Returns:
            Dict: {"success_count": int, "failed_count": int, "failed_records": List[dict]}
        """
        # --- 1. UP-FRONT VALIDATION (Atomicity Check) ---
        errors = []
        
        # Check empty list
        if not records_data:
            return {
                "success_count": 0,
                "failed_count": 0,
                "failed_records": []
            }
            
        # Cache existing employees and teams to avoid N+1 queries during validation
        employees_cache = {}
        teams_cache = {}
        
        for idx, rec in enumerate(records_data):
            required = ["employee_id", "team_id", "month", "year", "score", "grade", "status"]
            missing = [f for f in required if f not in rec]
            if missing:
                errors.append(f"Record at index {idx} missing required fields: {', '.join(missing)}")
                continue
                
            # Validate score range
            try:
                score = float(rec["score"])
                if not (0 <= score <= 100):
                    errors.append(f"Record at index {idx} score {score} is out of bounds (0-100).")
            except (ValueError, TypeError):
                errors.append(f"Record at index {idx} score must be a numeric value.")
                
            # Validate grade and status
            if rec["grade"] not in ["A", "B", "C", "D", "E"]:
                errors.append(f"Record at index {idx} has invalid grade: {rec['grade']}.")
            if rec["status"] not in ["Exceeds", "Meets", "Below"]:
                errors.append(f"Record at index {idx} has invalid status: {rec['status']}.")
                
            # Validate employee
            emp_key = rec["employee_id"]
            if emp_key not in employees_cache:
                emp_uuid = emp_key
                if isinstance(emp_key, str):
                    try:
                        emp_uuid = uuid.UUID(emp_key)
                    except ValueError:
                        pass
                emp = db.query(Employee).filter(Employee.id == emp_uuid).first()
                if not emp:
                    emp = db.query(Employee).filter(Employee.employee_id == emp_key).first()
                employees_cache[emp_key] = emp
                
            if not employees_cache[emp_key]:
                errors.append(f"Record at index {idx} references non-existent employee '{emp_key}'.")
                
            # Validate team
            team_key = rec["team_id"]
            if team_key not in teams_cache:
                team_uuid = team_key
                if isinstance(team_key, str):
                    try:
                        team_uuid = uuid.UUID(team_key)
                    except ValueError:
                        pass
                team = db.query(Team).filter(Team.id == team_uuid).first()
                if not team:
                    team = db.query(Team).filter(
                        Team.name == team_key,
                        Team.team_level == "employee",
                    ).first()
                teams_cache[team_key] = team
                
            if not teams_cache[team_key]:
                errors.append(f"Record at index {idx} references non-existent team '{team_key}'.")
                
        # If any validation errors exist, fail the entire batch immediately (atomicity)
        if errors:
            return {
                "success_count": 0,
                "failed_count": len(errors),
                "failed_records": [{"index": i, "error": err} for i, err in enumerate(errors[:100])]
            }
            
        # --- 2. CHUNKED TRANSACTION PROCESSING ---
        success_count = 0
        failed_count = 0
        failed_records = []
        
        # Split into chunks of 1,000
        chunk_size = 1000
        chunks = [records_data[i:i + chunk_size] for i in range(0, len(records_data), chunk_size)]
        
        for chunk in chunks:
            # Chunk transaction block
            try:
                # begin_nested starts a SAVEPOINT in DB
                with db.begin_nested():
                    for rec in chunk:
                        # Per-record nested savepoint for custom isolation
                        try:
                            with db.begin_nested():
                                emp = employees_cache[rec["employee_id"]]
                                team = teams_cache[rec["team_id"]]
                                
                                perf_record = PerformanceRecord(
                                    employee_id=emp.id,
                                    team_id=team.id,
                                    month=rec["month"],
                                    year=rec["year"],
                                    score=rec["score"],
                                    grade=rec["grade"],
                                    status=rec["status"]
                                )
                                db.add(perf_record)
                                db.flush()  # Populates primary key (UUID) and check constraints
                                
                                # Insert KPI values if they exist
                                if "kpi_values" in rec and rec["kpi_values"]:
                                    for kv in rec["kpi_values"]:
                                        kpi_val = KPIValue(
                                            record_id=perf_record.id,
                                            record_year=perf_record.year,
                                            kpi_key=kv["kpi_key"],
                                            actual_value=kv["actual_value"],
                                            target_value=kv["target_value"],
                                            achievement_ratio=kv.get("achievement_ratio", 0.0),
                                            weight_applied=kv.get("weight_applied", 0.0),
                                            contribution=kv.get("contribution", 0.0)
                                        )
                                        db.add(kpi_val)
                                
                                # Log audit record
                                AuditService.log_operation(
                                    db=db,
                                    table_name="performance_records",
                                    operation="INSERT",
                                    record_id=str(perf_record.id),
                                    new_values={
                                        "employee_id": str(emp.id),
                                        "team_id": str(team.id),
                                        "month": rec["month"],
                                        "year": rec["year"],
                                        "score": float(rec["score"]),
                                        "grade": rec["grade"],
                                        "status": rec["status"]
                                    },
                                    performed_by_user_id=performed_by_user_id
                                )
                                success_count += 1
                        except Exception as rec_err:
                            failed_count += 1
                            if len(failed_records) < 100:
                                failed_records.append({
                                    "record": rec,
                                    "error": str(rec_err)
                                })
            except Exception as chunk_err:
                # Roll back the entire chunk transaction
                failed_count += len(chunk)
                for rec in chunk:
                    if len(failed_records) < 100:
                        failed_records.append({
                            "record": rec,
                            "error": f"Chunk-level transaction error: {chunk_err}"
                        })
                        
        db.commit()
        return {
            "success_count": success_count,
            "failed_count": failed_count,
            "failed_records": failed_records
        }

    @staticmethod
    def batch_update_kpi_weights(
        db: Session,
        team_id: str,
        updates: List[Dict[str, Any]],
        performed_by_user_id: str = None,
        performance_level: str = "Employee",
        position_name: str = "",
    ) -> Dict[str, Any]:
        """
        Validate weights up-front (sum must equal 1.0 within 0.01 tolerance)
        and updates them in a single transaction.
        
        Args:
            db: Database session
            team_id: Team UUID
            updates: List of update dicts {"kpi_key": str, "weight": float, ...}
            performed_by_user_id: ID of user performing updates
            
        Returns:
            Dict: {"success": bool, "errors": List[str]}
        """
        errors = []
        
        try:
            team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
            
            # Fetch existing KPI configs
            performance_level = normalize_performance_level(performance_level)
            configs = db.query(TeamKPIConfig).filter(
                TeamKPIConfig.team_id == team_uuid,
                TeamKPIConfig.performance_level == performance_level,
                TeamKPIConfig.position_name == position_name,
            ).all()
            if not configs:
                errors.append(f"No KPI configurations found for team {team_id}.")
                return {"success": False, "errors": errors}

            # Build a merged dictionary of weights
            weights_map = {config.kpi_key: float(config.weight) for config in configs}
            
            # Update values
            for up in updates:
                k_key = up.get("kpi_key")
                k_weight = up.get("weight")
                if k_key is None or k_weight is None:
                    errors.append("Each update must contain 'kpi_key' and 'weight'.")
                    return {"success": False, "errors": errors}
                weights_map[k_key] = float(k_weight)
                
            # Weight totals are independent for each team + performance level + position.
            total_weight = sum(weights_map.values())
            if abs(total_weight - 1.0) > 0.01:
                if total_weight > 1.0:
                    errors.append(
                        f"{performance_level}/{position_name or 'default'} KPI weights exceed 1.0 "
                        f"(got {total_weight:.3f})."
                    )
                else:
                    errors.append(
                        f"{performance_level}/{position_name or 'default'} KPI weights "
                        f"must equal 1.0 (got {total_weight:.3f})."
                    )
                return {"success": False, "errors": errors}

            # Apply updates inside a transaction block
            with db.begin_nested():
                for up in updates:
                    config = next((c for c in configs if c.kpi_key == up["kpi_key"]), None)
                    if config:
                        old_values = {"weight": float(config.weight)}
                        config.weight = up["weight"]
                        new_values = {"weight": float(up["weight"])}
                        
                        # Log change to audit
                        AuditService.log_operation(
                            db=db,
                            table_name="team_kpi_config",
                            operation="UPDATE",
                            record_id=str(config.id),
                            old_values=old_values,
                            new_values=new_values,
                            performed_by_user_id=performed_by_user_id
                        )
            db.commit()
            return {"success": True, "errors": []}
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to batch update KPI weights for team {team_id}: {e}")
            return {"success": False, "errors": [str(e)]}
