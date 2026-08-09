"""Integration tests for QueryOptimizer
"""

import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from models.models import Base, User, Employee, Team, PerformanceRecord, KPIValue
from services.query_optimizer import QueryOptimizer


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        Employee.__table__,
        Team.__table__,
        PerformanceRecord.__table__,
        KPIValue.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestQueryOptimizer:
    """Integration tests for QueryOptimizer performance and pagination queries"""

    def test_get_performance_records_eager_loading(self, db_session):
        """Verify performance records query successfully eager-loads relationships"""
        # Create seed data
        team = Team(id=uuid.uuid4(), name="Inbound", db_name="inbound_db", region="UAE")
        emp = Employee(id=uuid.uuid4(), employee_id="emp001", name="John Doe", team_id=team.id, region="UAE")
        rec = PerformanceRecord(
            id=uuid.uuid4(),
            year=2026,
            employee_id=emp.id,
            team_id=team.id,
            month="January",
            score=92.5,
            grade="A",
            status="Exceeds"
        )
        kpi = KPIValue(
            id=uuid.uuid4(),
            record_id=rec.id,
            record_year=2026,
            kpi_key="quality",
            actual_value=95.0,
            target_value=90.0,
            achievement_ratio=1.05,
            weight_applied=0.4,
            contribution=38.0
        )
        db_session.add_all([team, emp, rec, kpi])
        db_session.commit()

        # Call get_performance_records through QueryOptimizer
        with patch("services.query_optimizer.CacheService.get_performance_cache") as mock_get_cache, \
             patch("services.query_optimizer.redis_client") as mock_redis:
            mock_get_cache.return_value = None
            
            results = QueryOptimizer.get_performance_records(
                db=db_session,
                employee_id=str(emp.id),
                month="January",
                year=2026,
                page=1,
                limit=10
            )
            
            assert len(results) == 1
            record = results[0]
            assert record["employee_name"] == "John Doe"
            assert len(record["kpi_values"]) == 1
            assert record["kpi_values"][0]["kpi_key"] == "quality"
            assert record["score"] == 92.5

    def test_get_team_performance_aggregated(self, db_session):
        """Verify aggregated query computes count, average, max, and min correctly"""
        team = Team(id=uuid.uuid4(), name="Inbound", db_name="inbound_db", region="UAE")
        emp1 = Employee(id=uuid.uuid4(), employee_id="emp001", name="John Doe", team_id=team.id)
        emp2 = Employee(id=uuid.uuid4(), employee_id="emp002", name="Jane Smith", team_id=team.id)
        
        rec1 = PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=emp1.id, team_id=team.id,
            month="January", score=90.0, grade="B", status="Meets"
        )
        rec2 = PerformanceRecord(
            id=uuid.uuid4(), year=2026, employee_id=emp2.id, team_id=team.id,
            month="January", score=80.0, grade="C", status="Meets"
        )
        
        db_session.add_all([team, emp1, emp2, rec1, rec2])
        db_session.commit()

        # Call aggregation under Mock cache
        with patch("services.query_optimizer.CacheService.get_team_performance_cache") as mock_get, \
             patch("services.query_optimizer.CacheService.set_team_performance_cache") as mock_set:
            mock_get.return_value = None
            
            stats = QueryOptimizer.get_team_performance_aggregated(db_session, str(team.id), "January", 2026)
            
            assert stats["total_records"] == 2
            assert stats["average_score"] == 85.0
            assert stats["max_score"] == 90.0
            assert stats["min_score"] == 80.0
            mock_set.assert_called_once_with(str(team.id), "January", 2026, stats)

    def test_list_employees_paginated(self, db_session):
        """Verify list_employees_paginated applies filtering, page offset, and caps limits"""
        team = Team(id=uuid.uuid4(), name="Inbound", db_name="inbound_db", region="UAE")
        db_session.add(team)
        db_session.commit()

        # Create 5 employees
        for i in range(5):
            emp = Employee(
                id=uuid.uuid4(),
                employee_id=f"emp_{i}",
                name=f"Employee {i}",
                team_id=team.id,
                is_active=(i < 4)  # 4 active, 1 inactive
            )
            db_session.add(emp)
        db_session.commit()

        # 1. Page 1, limit 2, default is_active = True
        res = QueryOptimizer.list_employees_paginated(db_session, str(team.id), page=1, limit=2)
        assert res["total"] == 4  # 4 active
        assert len(res["data"]) == 2
        assert res["total_pages"] == 2
        assert res["page"] == 1

        # 2. Limit cap testing (should be capped at 100)
        res_large = QueryOptimizer.list_employees_paginated(db_session, str(team.id), page=1, limit=500)
        assert res_large["page_size"] == 100

        # 3. Include deleted employees
        res_all = QueryOptimizer.list_employees_paginated(db_session, str(team.id), page=1, limit=10, include_deleted=True)
        assert res_all["total"] == 5
        assert len(res_all["data"]) == 5
