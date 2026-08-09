"""Query Optimizer Service
Provides optimized database query operations with eager loading, caching, and paging constraints.
"""

import json
import logging
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from models.models import PerformanceRecord, Employee
from services.cache_service import CacheService, redis_client

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Enterprise database query optimization and caching layer"""

    @staticmethod
    def get_performance_records(
        db: Session,
        employee_id: str,
        month: str,
        year: int,
        page: int = 1,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get performance records with eager loading and pagination.
        Optimized via Redis cache and employee_id/month/year index.
        """
        # Enforce page/limit boundaries
        if page < 1:
            page = 1
        if limit > 100:
            limit = 100
        elif limit < 1:
            limit = 10

        # 1. Try cache first
        cache_key = f"performance:{employee_id}:{month}:{year}:{page}"
        cached_data = CacheService.get_performance_cache(employee_id, month, year)
        # Note: CacheService key format is performance:{employee_id}:{month}:{year}
        # Let's read from Redis directly via CacheService's client if available, or fallback
        if redis_client:
            try:
                val = redis_client.get(cache_key)
                if val:
                    logger.info("cache hit", extra={"cache_key": cache_key, "cache_type": "paginated_performance"})
                    return json.loads(val)
                logger.info("cache miss", extra={"cache_key": cache_key, "cache_type": "paginated_performance"})
            except Exception as e:
                logger.warning(f"Failed to read paginated performance cache: {e}")

        # 2. Database query with eager loading (joinedload)
        offset = (page - 1) * limit
        try:
            # Convert employee_id to uuid if string
            emp_uuid = uuid.UUID(employee_id) if isinstance(employee_id, str) else employee_id
        except ValueError:
            return []

        records = (
            db.query(PerformanceRecord)
            .options(
                joinedload(PerformanceRecord.employee),
                joinedload(PerformanceRecord.kpi_values)
            )
            .filter(
                PerformanceRecord.employee_id == emp_uuid,
                PerformanceRecord.month == month,
                PerformanceRecord.year == year
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Serialize results to cache-friendly format
        serialized_records = []
        for r in records:
            record_dict = {
                "id": str(r.id),
                "employee_id": str(r.employee_id),
                "employee_name": r.employee.name if r.employee else "",
                "team_id": str(r.team_id),
                "month": r.month,
                "year": r.year,
                "score": float(r.score),
                "grade": r.grade,
                "status": r.status,
                "kpi_values": [
                    {
                        "kpi_key": kv.kpi_key,
                        "actual_value": float(kv.actual_value),
                        "target_value": float(kv.target_value),
                        "achievement_ratio": min(max(float(kv.achievement_ratio), 0.0), 1.0),
                        "weight_applied": float(kv.weight_applied or 0),
                        "contribution": min(max(float(kv.contribution or 0), 0.0), max(float(kv.weight_applied or 0), 0.0)),
                        "cap_achievement": True,
                    }
                    for kv in r.kpi_values
                ]
            }
            serialized_records.append(record_dict)

        # 3. Cache the serialized list
        if redis_client:
            try:
                redis_client.set(cache_key, json.dumps(serialized_records), ex=3600)
                logger.info("cache set", extra={"cache_key": cache_key, "cache_type": "paginated_performance", "ttl": 3600})
            except Exception as e:
                logger.warning(f"Failed to cache paginated performance records: {e}")

        return serialized_records

    @staticmethod
    def get_team_performance_aggregated(
        db: Session,
        team_id: str,
        month: str,
        year: int
    ) -> Dict[str, Any]:
        """
        Get aggregated team performance stats using optimized grouping queries.
        Result is cached via Redis.
        """
        # Try cache first
        cached_data = CacheService.get_team_performance_cache(team_id, month, year)
        if cached_data:
            logger.info("cache hit", extra={"cache_key": f"team_performance:{team_id}:{month}:{year}", "cache_type": "team_aggregate"})
            return cached_data

        try:
            team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
        except ValueError:
            return {
                "total_records": 0,
                "average_score": 0.0,
                "max_score": 0.0,
                "min_score": 0.0
            }

        # Query stats from database in a single aggregation
        result = (
            db.query(
                func.count(PerformanceRecord.id).label("total_records"),
                func.avg(PerformanceRecord.score).label("avg_score"),
                func.max(PerformanceRecord.score).label("max_score"),
                func.min(PerformanceRecord.score).label("min_score")
            )
            .filter(
                PerformanceRecord.team_id == team_uuid,
                PerformanceRecord.month == month,
                PerformanceRecord.year == year
            )
            .first()
        )

        aggregated = {
            "total_records": result.total_records or 0,
            "average_score": float(result.avg_score) if result.avg_score else 0.0,
            "max_score": float(result.max_score) if result.max_score else 0.0,
            "min_score": float(result.min_score) if result.min_score else 0.0,
        }

        position_rows = (
            db.query(
                PerformanceRecord.position_name,
                func.count(PerformanceRecord.id).label("total_records"),
                func.avg(PerformanceRecord.score).label("avg_score"),
                func.max(PerformanceRecord.score).label("max_score"),
                func.min(PerformanceRecord.score).label("min_score"),
            )
            .filter(
                PerformanceRecord.team_id == team_uuid,
                PerformanceRecord.month == month,
                PerformanceRecord.year == year,
                PerformanceRecord.position_name.isnot(None),
                PerformanceRecord.position_name != "",
            )
            .group_by(PerformanceRecord.position_name)
            .all()
        )
        aggregated["by_position"] = {
            row.position_name: {
                "total_records": row.total_records or 0,
                "average_score": float(row.avg_score) if row.avg_score else 0.0,
                "max_score": float(row.max_score) if row.max_score else 0.0,
                "min_score": float(row.min_score) if row.min_score else 0.0,
            }
            for row in position_rows
        }

        # Save to cache
        CacheService.set_team_performance_cache(team_id, month, year, aggregated)

        return aggregated

    @staticmethod
    def list_employees_paginated(
        db: Session,
        team_id: str,
        page: int = 1,
        limit: int = 100,
        include_deleted: bool = False
    ) -> Dict[str, Any]:
        """
        List employees in a team with pagination. Enforces limit <= 100.
        Respects active status filter by default.
        """
        if page < 1:
            page = 1
        if limit > 100:
            limit = 100
        elif limit < 1:
            limit = 10

        try:
            team_uuid = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
        except ValueError:
            return {
                "data": [],
                "total": 0,
                "page": page,
                "page_size": limit,
                "total_pages": 0
            }

        # Filter construction
        query_filter = [Employee.team_id == team_uuid]
        if not include_deleted:
            query_filter.append(Employee.is_active == True)

        # Count total records matching criteria
        total = db.query(func.count(Employee.id)).filter(*query_filter).scalar()

        # Paginated fetch
        offset = (page - 1) * limit
        employees = (
            db.query(Employee)
            .filter(*query_filter)
            .offset(offset)
            .limit(limit)
            .all()
        )

        data = [
            {
                "id": str(emp.id),
                "employee_id": emp.employee_id,
                "name": emp.name,
                "team_id": str(emp.team_id),
                "region": emp.region,
                "is_active": emp.is_active
            }
            for emp in employees
        ]

        total_pages = (total + limit - 1) // limit if limit > 0 else 0

        return {
            "data": data,
            "total": total,
            "page": page,
            "page_size": limit,
            "total_pages": total_pages
        }
