"""Bulk Operations Router
Exposes high-performance batch endpoints protected by RBAC permissions.
"""

import logging
from typing import Dict, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from config.database import get_db
from models.schemas import StandardResponse
from api.middleware.rbac_middleware import require_permission
from services.batch_processor import BatchProcessor
from services.soft_delete_service import SoftDeleteService
from services.cache_service import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bulk", tags=["Bulk Operations"])


@router.post("/performance/records", response_model=StandardResponse, status_code=status.HTTP_201_CREATED)
async def bulk_insert_performance_records(
    payload: List[Dict[str, Any]],
    request: Request,
    db: Session = Depends(get_db),
    user_payload: dict = Depends(require_permission("upload_data"))
):
    """
    Bulk insert performance records with upfront validation (atomicity).
    """
    try:
        performed_by_user_id = user_payload.get("user_id")
        result = BatchProcessor.batch_insert_performance_records(
            db=db,
            records_data=payload,
            performed_by_user_id=performed_by_user_id
        )
        
        # If no records were successfully inserted but validation errors occurred
        if result["success_count"] == 0 and result["failed_count"] > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Batch insert failed validation checks.",
                    "failed_records": result["failed_records"]
                }
            )
            
        return StandardResponse(
            success=True,
            message=f"Batch insert completed. Success: {result['success_count']}, Failed: {result['failed_count']}",
            data=result
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Bulk performance insert error: {e}")
        return StandardResponse(
            success=False,
            message="Failed to process bulk insert."
        )


@router.patch("/teams/{team_id}/kpi-config", response_model=StandardResponse)
async def bulk_update_kpi_weights(
    team_id: str,
    payload: List[Dict[str, Any]],
    request: Request,
    db: Session = Depends(get_db),
    user_payload: dict = Depends(require_permission("edit_team_config")),
    performance_level: str = Query("Employee"),
    position: str = Query(""),
):
    """
    Bulk update KPI weights for a team, validating that the new weights sum to 1.0.
    """
    try:
        performed_by_user_id = user_payload.get("user_id")
        result = BatchProcessor.batch_update_kpi_weights(
            db=db,
            team_id=team_id,
            updates=payload,
            performed_by_user_id=performed_by_user_id,
            performance_level=performance_level,
            position_name=position,
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="; ".join(result["errors"])
            )
            
        return StandardResponse(
            success=True,
            message="KPI weights updated successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Bulk KPI update error: {e}")
        return StandardResponse(
            success=False,
            message="Failed to update KPI weights."
        )


@router.delete("/employees", response_model=StandardResponse)
async def bulk_delete_employees(
    payload: Dict[str, List[str]],
    request: Request,
    db: Session = Depends(get_db),
    user_payload: dict = Depends(require_permission("delete_team"))
):
    """
    Bulk soft-delete employee records (limit 100).
    """
    try:
        employee_ids = payload.get("employee_ids", [])
        if not employee_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="employee_ids list is required"
            )
            
        if len(employee_ids) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot bulk delete more than 100 employees at a time"
            )
            
        performed_by_user_id = user_payload.get("user_id")
        success_count = 0
        failed_ids = []
        
        # Execute deletions
        for emp_id in employee_ids:
            success = SoftDeleteService.soft_delete_employee(
                db=db,
                employee_id=emp_id,
                performed_by_user_id=performed_by_user_id
            )
            if success:
                success_count += 1
                # Invalidate Redis cache keys for the employee's performance records
                if redis_client:
                    try:
                        keys = list(redis_client.scan_iter(match=f"performance:{emp_id}:*"))
                        if keys:
                            redis_client.delete(*keys)
                    except Exception as cache_ex:
                        logger.warning(f"Failed to delete cache keys for {emp_id}: {cache_ex}")
            else:
                failed_ids.append(emp_id)
        
        if failed_ids:
            return StandardResponse(
                success=True,
                message=f"Bulk delete completed with partial failures. Deleted: {success_count}. Failed: {len(failed_ids)}.",
                data={"failed_ids": failed_ids}
            )
            
        return StandardResponse(
            success=True,
            message=f"Successfully bulk deleted {success_count} employees"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Bulk employee delete error: {e}")
        return StandardResponse(
            success=False,
            message="Failed to process bulk employee delete."
        )
