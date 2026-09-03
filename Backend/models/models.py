import uuid
from sqlalchemy import Column, String, Integer, SmallInteger, Numeric, Boolean, Date, DateTime, ForeignKey, Text, LargeBinary, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Enum as SQLEnum, JSON, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base
from utils.performance_levels import PerformanceLevel
from utils.user_identity import default_user_full_name


JSON_COMPAT_TYPE = JSON().with_variant(JSONB, "postgresql")
INET_COMPAT_TYPE = String(45).with_variant(INET, "postgresql")

# ============================================================
# 1. CONFIGURATION MODELS
# ============================================================

class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    db_name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    region = Column(String(10), nullable=False, default="UAE")
    team_level = Column(String(20), nullable=False, default="employee")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    employees = relationship("Employee", back_populates="team")

    __table_args__ = (
        CheckConstraint(
            "team_level IN ('employee', 'management')",
            name="ck_team_level",
        ),
        Index(
            "uq_team_logical_level_ci",
            func.lower(func.coalesce(display_name, name)),
            team_level,
            unique=True,
        ),
        Index("idx_team_scope_lookup", "display_name", "team_level", "is_active"),
    )


class TeamKPIConfig(Base):
    __tablename__ = "team_kpi_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    performance_level = Column(String(20), nullable=False, default=PerformanceLevel.EMPLOYEE.value, server_default=PerformanceLevel.EMPLOYEE.value)
    position_name = Column(String(255), nullable=False, default="", server_default="")
    perspective = Column(String(50), nullable=True)
    kpi_key = Column(String(50), nullable=False)
    kpi_label = Column(String(100), nullable=False)
    weight = Column(Numeric(5, 4), nullable=False)
    direction = Column(String(20), nullable=False, default="higher_better")  # maps to enum kpi_direction
    unit = Column(String(20), nullable=False, default="%")
    color = Column(String(20), nullable=False, default="#10B981")
    actual_col = Column(String(100), nullable=False)
    target_col = Column(String(100), nullable=False)
    achievement_col = Column(String(100), nullable=True)
    volume_unit = Column(String(20), nullable=True)
    display_order = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint('team_id', 'performance_level', 'position_name', 'kpi_key', name='uq_kpi_team_level_position_key'),
        CheckConstraint(f"performance_level IN ('{PerformanceLevel.EMPLOYEE.value}', '{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')", name='ck_team_kpi_performance_level'),
        Index('idx_kpi_config_team_level', 'team_id', 'performance_level', 'position_name'),
    )


class ManagementKPIConfig(Base):
    __tablename__ = "management_kpi_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    performance_level = Column(String(20), nullable=False)
    position_name = Column(String(255), nullable=True)
    employee_identifier = Column(String(50), nullable=True)
    perspective_key = Column(String(50), nullable=False)
    kpi_key = Column(String(100), nullable=False)
    kpi_label = Column(String(255), nullable=False)
    direction = Column(String(20), nullable=False, default="higher_better")
    weight = Column(Numeric(7, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=True)
    target_unit = Column(String(20), nullable=True, default="%")
    display_order = Column(SmallInteger, nullable=False, default=0)
    effective_month = Column(String(20), nullable=False)
    effective_year = Column(SmallInteger, nullable=False)
    upload_batch_id = Column(UUID(as_uuid=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "performance_level",
            "effective_month",
            "effective_year",
            "position_name",
            "employee_identifier",
            "kpi_key",
            name="uq_management_kpi_config_scope",
        ),
        CheckConstraint(
            f"performance_level IN ('{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')",
            name="ck_management_kpi_config_level",
        ),
        CheckConstraint(
            "((position_name IS NOT NULL AND employee_identifier IS NULL) OR "
            "(position_name IS NULL AND employee_identifier IS NOT NULL))",
            name="ck_management_kpi_config_scope",
        ),
        CheckConstraint("weight > 0", name="ck_management_kpi_config_weight_positive"),
        Index(
            "idx_management_kpi_config_lookup",
            "team_id",
            "performance_level",
            "effective_year",
            "effective_month",
            "position_name",
            "employee_identifier",
        ),
        Index("idx_management_kpi_config_batch", "upload_batch_id"),
    )


class ManagementKPIConfigHistory(Base):
    __tablename__ = "management_kpi_config_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(20), nullable=False, default="replace")
    old_values = Column(JSON_COMPAT_TYPE, nullable=True)
    new_values = Column(JSON_COMPAT_TYPE, nullable=True)
    upload_batch_id = Column(UUID(as_uuid=True), nullable=True)
    source_filename = Column(String(255), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_management_kpi_config_history_team", "team_id", "changed_at"),
        Index("idx_management_kpi_config_history_batch", "upload_batch_id"),
    )


class ManagementKPISnapshot(Base):
    __tablename__ = "management_kpi_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    employee_identifier = Column(String(50), nullable=False)
    employee_name = Column(String(255), nullable=False)
    position_name = Column(String(255), nullable=False)
    performance_level = Column(String(20), nullable=False)
    month = Column(String(20), nullable=False)
    year = Column(SmallInteger, nullable=False)
    perspective_key = Column(String(50), nullable=False)
    kpi_key = Column(String(100), nullable=False)
    kpi_label = Column(String(255), nullable=False)
    actual_value = Column(Numeric(18, 4), nullable=True)
    upload_batch_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "team_id",
            "employee_identifier",
            "performance_level",
            "month",
            "year",
            "kpi_key",
            name="uq_management_kpi_snapshot_scope",
        ),
        CheckConstraint(
            f"performance_level IN ('{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')",
            name="ck_management_kpi_snapshot_level",
        ),
        Index(
            "idx_management_kpi_snapshot_lookup",
            "team_id",
            "performance_level",
            "year",
            "month",
        ),
        Index("idx_management_kpi_snapshot_batch", "upload_batch_id"),
    )


# ============================================================
# 2. CORE EMPLOYEES MODEL
# ============================================================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String(50), nullable=False, unique=True)  # From Excel
    name = Column(String(255), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    region = Column(String(10), nullable=False, default="UAE")
    performance_level = Column(String(20), nullable=False, default=PerformanceLevel.EMPLOYEE.value, server_default=PerformanceLevel.EMPLOYEE.value)
    position_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team = relationship("Team", back_populates="employees")
    performance_records = relationship("PerformanceRecord", back_populates="employee")

    __table_args__ = (
        CheckConstraint(f"performance_level IN ('{PerformanceLevel.EMPLOYEE.value}', '{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')", name='ck_employee_performance_level'),
        Index('idx_employee_perf_level', 'performance_level'),
    )


# ============================================================
# 3. PERFORMANCE & LOG MODELS
# ============================================================

class EmployeeUploadBatch(Base):
    """One user-uploaded employee PMS workbook.

    A workbook can contain many teams and months.  UploadLog remains the
    per-team/per-period audit detail, while this row is the unit shown to and
    deleted by administrators.
    """

    __tablename__ = "employee_upload_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    record_count = Column(Integer, nullable=False, default=0)
    team_count = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="processing")
    uploaded_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    uploaded_by_name = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    upload_logs = relationship(
        "UploadLog",
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UploadLog(Base):
    __tablename__ = "upload_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employee_upload_batches.id", ondelete="CASCADE"),
        nullable=True,
    )
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    month = Column(String(20), nullable=False)
    year = Column(SmallInteger, nullable=False)
    record_count = Column(Integer, nullable=False, default=0)
    uploaded_by_user_id = Column(UUID(as_uuid=True), nullable=True)  # Linked to users if auth enabled
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team")
    batch = relationship("EmployeeUploadBatch", back_populates="upload_logs")

    __table_args__ = (
        Index("idx_upload_log_batch", "batch_id"),
    )


class ProcessingJob(Base):
    """Durable state for work that must outlive the HTTP request process."""

    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_by_name = Column(String(255), nullable=True)
    request_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    input_path = Column(String(500), nullable=True)
    progress = Column(SmallInteger, nullable=False, default=0)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    worker_id = Column(String(150), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    result_type = Column(String(60), nullable=True)
    result_id = Column(String(100), nullable=True)
    result_json = Column(JSON_COMPAT_TYPE, nullable=True)
    error_code = Column(String(80), nullable=True)
    safe_error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('pms_upload', 'report_generation', 'story_report_generation')",
            name="ck_processing_job_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_processing_job_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_processing_job_progress"),
        CheckConstraint("attempt_count >= 0", name="ck_processing_job_attempts"),
        CheckConstraint("max_attempts >= 1", name="ck_processing_job_max_attempts"),
        UniqueConstraint("kind", "idempotency_key", name="uq_processing_job_idempotency"),
        Index("idx_processing_job_claim", "status", "available_at", "created_at"),
        Index("idx_processing_job_requester", "requested_by_user_id", "created_at"),
    )


class PerformanceRecord(Base):
    __tablename__ = "performance_records"

    # Composite Primary Key for Partitioning support
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year = Column(SmallInteger, primary_key=True, nullable=False)  # Partition Key
    
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    month = Column(String(20), nullable=False)
    performance_level = Column(String(20), nullable=False, default=PerformanceLevel.EMPLOYEE.value, server_default=PerformanceLevel.EMPLOYEE.value)
    position_name = Column(String(255), nullable=True)
    region = Column(String(10), nullable=True)
    score = Column(Numeric(6, 2), nullable=False)
    grade = Column(String(5), nullable=False)  # A, B, C, D, E
    status = Column(String(20), nullable=False)  # Exceeds, Meets, Below
    upload_id = Column(UUID(as_uuid=True), ForeignKey("upload_log.id", ondelete="SET NULL"), nullable=True)
    # Full normalized record contract used by employee dashboards.  The
    # relational score/KPI columns stay queryable; this payload preserves the
    # Excel evidence (calls, geo, actuals and raw columns) without JSON files.
    record_payload = Column(JSON_COMPAT_TYPE, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    employee = relationship("Employee", back_populates="performance_records")
    team = relationship("Team")
    kpi_values = relationship("KPIValue", back_populates="performance_record")

    __table_args__ = (
        CheckConstraint(f"performance_level IN ('{PerformanceLevel.EMPLOYEE.value}', '{PerformanceLevel.MANAGERIAL.value}', '{PerformanceLevel.CORPORATE.value}')", name='ck_performance_record_level'),
        Index('idx_perf_record_filters', 'team_id', 'performance_level', 'month', 'year'),
    )


class KPIValue(Base):
    __tablename__ = "kpi_values"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    record_year = Column(SmallInteger, nullable=False)  # Required to match parent composite key
    kpi_key = Column(String(50), nullable=False)
    actual_value = Column(Numeric(18, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=False)
    achievement_ratio = Column(Numeric(10, 4), nullable=False)
    weight_applied = Column(Numeric(5, 4), nullable=False)
    contribution = Column(Numeric(7, 4), nullable=False)

    # Composite Foreign Key constraints
    __table_args__ = (
        ForeignKeyConstraint(
            ['record_id', 'record_year'], 
            ['performance_records.id', 'performance_records.year'], 
            ondelete="CASCADE"
        ),
    )

    # Relationships
    performance_record = relationship("PerformanceRecord", back_populates="kpi_values")


# ============================================================
# 4. AUTHENTICATION & AUTHORIZATION MODELS
# ============================================================

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(50), nullable=False)
    permission = Column(String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint('role', 'permission', name='uq_role_permission'),
    )

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(String(50), nullable=True)  # References employees.employee_id
    full_name = Column(String(255), nullable=False, default=default_user_full_name)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(50), nullable=False, default="Viewer")  # Admin, Manager, Executive, Viewer
    is_active = Column(Boolean, nullable=False, default=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team_assignments = relationship("UserTeamAssignment", back_populates="user", passive_deletes=True)
    notifications = relationship("NotificationRecipient", back_populates="user", passive_deletes=True)
    actions_created = relationship(
        "Action",
        foreign_keys="Action.created_by_user_id",
        back_populates="created_by_user",
        passive_deletes=True,
    )
    actions_updated = relationship(
        "Action",
        foreign_keys="Action.updated_by_user_id",
        back_populates="updated_by_user",
        passive_deletes=True,
    )
    # ponytail: keep deletes from loading audit rows when the live DB lags schema updates
    audit_logs = relationship("AuditLog", back_populates="performed_by_user", passive_deletes=True)
    refresh_sessions = relationship(
        "RefreshSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class RefreshSession(Base):
    """Durable, rotating browser refresh session.

    Raw refresh and CSRF values are never persisted. The hashes are enough to
    validate a browser session while keeping a database read compromise from
    becoming an immediately usable authentication credential.
    """

    __tablename__ = "refresh_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id = Column(UUID(as_uuid=True), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    csrf_token_hash = Column(String(64), nullable=False)
    parent_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    replaced_by_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    remember_me = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(String(80), nullable=True)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(INET_COMPAT_TYPE, nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="refresh_sessions", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_refresh_session_user_active", "user_id", "revoked_at", "expires_at"),
        Index("idx_refresh_session_family", "family_id"),
        Index("idx_refresh_session_parent", "parent_session_id"),
    )


class UserTeamAssignment(Base):
    __tablename__ = "user_team_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    performance_level = Column(String(20), nullable=True)
    access_level = Column(String(20), nullable=False, default="read")  # read, write, admin
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(100), nullable=False)

    # Relationships
    user = relationship("User", back_populates="team_assignments")
    team = relationship("Team")

    __table_args__ = (
        CheckConstraint(
            "performance_level IS NULL OR performance_level IN ('Employee', 'Managerial', 'Corporate')",
            name="ck_user_team_assignment_performance_level",
        ),
        Index("idx_user_team_assignment_scope", "user_id", "team_id", "performance_level"),
    )


# ============================================================
# 5. CONFIGURATION - GRADE THRESHOLDS
# ============================================================

class GradeThreshold(Base):
    __tablename__ = "grade_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    grade_a = Column(Numeric(5, 2), nullable=False, default=95)
    grade_b = Column(Numeric(5, 2), nullable=False, default=85)
    grade_c = Column(Numeric(5, 2), nullable=False, default=75)
    grade_d = Column(Numeric(5, 2), nullable=False, default=65)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String(100), nullable=True)

    # Relationships
    team = relationship("Team")


class KPIWeightHistory(Base):
    __tablename__ = "kpi_weight_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    kpi_key = Column(String(50), nullable=False)
    old_weight = Column(Numeric(5, 4), nullable=False)
    new_weight = Column(Numeric(5, 4), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(100), nullable=False)
    reason = Column(Text, nullable=True)

    # Relationships
    team = relationship("Team")


# ============================================================
# 6. ACTIONS - MANAGER INTERVENTIONS
# ============================================================

class PerformancePlan(Base):
    __tablename__ = "performance_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(180), nullable=False)
    scope_type = Column(String(20), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    performance_level = Column(String(20), nullable=False)
    region = Column(String(10), nullable=True)
    position_name = Column(String(255), nullable=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    baseline_value = Column(Numeric(18, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=False)
    current_value = Column(Numeric(18, 4), nullable=True)
    outcome_unit = Column(String(30), nullable=False, default="%")
    outcome_direction = Column(String(20), nullable=False, default="higher_better")
    expected_impact = Column(Numeric(18, 4), nullable=True)
    actual_impact = Column(Numeric(18, 4), nullable=True)
    status = Column(String(20), nullable=False, default="Draft")
    status_reason = Column(Text, nullable=True)
    no_insight_reason = Column(Text, nullable=True)
    completion_date = Column(Date, nullable=True)
    completion_note = Column(Text, nullable=True)
    completed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    team = relationship("Team")
    employee = relationship("Employee")
    owner = relationship("User", foreign_keys=[owner_user_id])
    completed_by = relationship("User", foreign_keys=[completed_by_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    objectives = relationship("PlanObjective", back_populates="plan", cascade="all, delete-orphan")
    kpis = relationship("PlanKPI", back_populates="plan", cascade="all, delete-orphan")
    milestones = relationship("PlanMilestone", back_populates="plan", cascade="all, delete-orphan")
    notes = relationship("PlanNote", back_populates="plan", cascade="all, delete-orphan")
    insight_links = relationship("PlanInsightLink", back_populates="plan", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="plan")

    __table_args__ = (
        CheckConstraint("scope_type IN ('Team', 'Position', 'Employee', 'Management')", name="ck_performance_plan_scope_type"),
        CheckConstraint("performance_level IN ('Employee', 'Managerial', 'Corporate')", name="ck_performance_plan_level"),
        CheckConstraint("status IN ('Draft', 'In Progress', 'At Risk', 'Completed', 'Archived')", name="ck_performance_plan_status"),
        CheckConstraint("outcome_direction IN ('higher_better', 'lower_better')", name="ck_performance_plan_direction"),
        CheckConstraint("period_end >= period_start", name="ck_performance_plan_period"),
        Index("idx_performance_plan_scope_status", "team_id", "performance_level", "status"),
    )


class PlanInsightLink(Base):
    __tablename__ = "plan_insight_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False)
    insight_id = Column(String(64), nullable=False)
    evidence_month = Column(String(20), nullable=False)
    evidence_year = Column(SmallInteger, nullable=False)
    linked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    plan = relationship("PerformancePlan", back_populates="insight_links")
    __table_args__ = (UniqueConstraint("plan_id", "insight_id", name="uq_plan_insight_link"),)


class PlanObjective(Base):
    __tablename__ = "plan_objectives"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    measurement_type = Column(String(30), nullable=False)
    baseline_value = Column(Numeric(18, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=False)
    current_value = Column(Numeric(18, 4), nullable=True)
    unit = Column(String(30), nullable=False)
    direction = Column(String(20), nullable=False)
    due_date = Column(Date, nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(20), nullable=False, default="Not Started")
    is_required = Column(Boolean, nullable=False, default=True)
    plan = relationship("PerformancePlan", back_populates="objectives")
    owner = relationship("User")
    kpi_links = relationship("PlanObjectiveKPI", back_populates="objective", cascade="all, delete-orphan")
    actions = relationship("Action", back_populates="objective")
    __table_args__ = (
        CheckConstraint("direction IN ('higher_better', 'lower_better')", name="ck_plan_objective_direction"),
        CheckConstraint("status IN ('Not Started', 'In Progress', 'Completed', 'At Risk')", name="ck_plan_objective_status"),
    )


class PlanKPI(Base):
    __tablename__ = "plan_kpis"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False)
    kpi_key = Column(String(100), nullable=False)
    kpi_label = Column(String(255), nullable=False)
    unit = Column(String(30), nullable=False)
    direction = Column(String(20), nullable=False)
    baseline_value = Column(Numeric(18, 4), nullable=False)
    target_value = Column(Numeric(18, 4), nullable=False)
    current_value = Column(Numeric(18, 4), nullable=True)
    contribution = Column(Numeric(18, 4), nullable=True)
    data_month = Column(String(20), nullable=True)
    data_year = Column(SmallInteger, nullable=True)
    plan = relationship("PerformancePlan", back_populates="kpis")
    objective_links = relationship("PlanObjectiveKPI", back_populates="kpi", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("plan_id", "kpi_key", name="uq_plan_kpi_key"),
        CheckConstraint("direction IN ('higher_better', 'lower_better')", name="ck_plan_kpi_direction"),
    )


class PlanObjectiveKPI(Base):
    __tablename__ = "plan_objective_kpis"
    objective_id = Column(UUID(as_uuid=True), ForeignKey("plan_objectives.id", ondelete="CASCADE"), primary_key=True)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("plan_kpis.id", ondelete="CASCADE"), primary_key=True)
    objective = relationship("PlanObjective", back_populates="kpi_links")
    kpi = relationship("PlanKPI", back_populates="objective_links")


class PlanMilestone(Base):
    __tablename__ = "plan_milestones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="Pending")
    completion_date = Column(Date, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    note = Column(Text, nullable=True)
    plan = relationship("PerformancePlan", back_populates="milestones")
    owner = relationship("User")
    __table_args__ = (CheckConstraint("status IN ('Pending', 'In Progress', 'Completed', 'Overdue')", name="ck_plan_milestone_status"),)


class PlanNote(Base):
    __tablename__ = "plan_notes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=False)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    text = Column(Text, nullable=False)
    review_month = Column(String(20), nullable=True)
    review_year = Column(SmallInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    plan = relationship("PerformancePlan", back_populates="notes")
    author = relationship("User")

class Action(Base):
    __tablename__ = "actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False)
    month = Column(String(20), nullable=False)
    year = Column(SmallInteger, nullable=False)
    action_type = Column(String(50), nullable=False)  # Training, Reward, PIP, Monitor, Coaching, Warning, Promotion
    plan_title = Column(String(255), nullable=True)
    action_text = Column(Text, nullable=False)
    root_cause_note = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="Open")  # Open, In Progress, Completed, Cancelled
    plan_id = Column(UUID(as_uuid=True), ForeignKey("performance_plans.id", ondelete="CASCADE"), nullable=True)
    objective_id = Column(UUID(as_uuid=True), ForeignKey("plan_objectives.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    priority = Column(String(20), nullable=True)
    linked_kpi_key = Column(String(100), nullable=True)
    completion_note = Column(Text, nullable=True)
    evidence_reference = Column(String(500), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    employee = relationship("Employee")
    team = relationship("Team")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id], back_populates="actions_created")
    updated_by_user = relationship("User", foreign_keys=[updated_by_user_id], back_populates="actions_updated")
    owner = relationship("User", foreign_keys=[owner_user_id])
    plan = relationship("PerformancePlan", back_populates="actions")
    objective = relationship("PlanObjective", back_populates="actions")


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(180), nullable=False)
    template_key = Column(String(100), nullable=False)
    report_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=False, default="")
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    visibility = Column(String(20), nullable=False, default="private")
    version = Column(Integer, nullable=False, default=1)
    definition_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    theme_key = Column(String(50), nullable=False, default="sgh_default")
    language = Column(String(10), nullable=False, default="en")
    preferred_format = Column(String(20), nullable=False, default="pdf")
    is_system_template = Column(Boolean, nullable=False, default=False)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("visibility IN ('private', 'organization')", name="ck_report_template_visibility"),
        CheckConstraint("preferred_format IN ('pdf', 'pptx')", name="ck_report_template_format"),
        CheckConstraint("version >= 1", name="ck_report_template_version"),
        UniqueConstraint("template_key", "version", name="uq_report_template_key_version"),
        Index("idx_report_template_owner_updated", "owner_user_id", "updated_at"),
        Index("idx_report_template_type_active", "report_type", "is_archived"),
    )


class ReportDraft(Base):
    __tablename__ = "report_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(180), nullable=False)
    report_type = Column(String(50), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True)
    template_version = Column(Integer, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="editing")
    primary_period_month = Column(String(20), nullable=False)
    primary_period_year = Column(SmallInteger, nullable=False)
    comparison_period_month = Column(String(20), nullable=True)
    comparison_period_year = Column(SmallInteger, nullable=True)
    scope_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    definition_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    management_commentary_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    validation_json = Column(JSON_COMPAT_TYPE, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    last_saved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('editing', 'ready', 'generated', 'archived')", name="ck_report_draft_status"),
        CheckConstraint("version >= 1", name="ck_report_draft_version"),
        Index("idx_report_draft_owner_updated", "owner_user_id", "updated_at"),
        Index("idx_report_draft_period_type", "primary_period_year", "primary_period_month", "report_type"),
    )


class GeneratedReport(Base):
    __tablename__ = "generated_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(180), nullable=False)
    report_type = Column(String(50), nullable=False)
    scope_summary = Column(String(255), nullable=False)
    period_label = Column(String(100), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    output_format = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="ready")
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    configuration = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    record_count = Column(Integer, nullable=False, default=0)
    warning = Column(Text, nullable=True)
    draft_id = Column(UUID(as_uuid=True), ForeignKey("report_drafts.id", ondelete="SET NULL"), nullable=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True)
    template_version = Column(Integer, nullable=True)
    primary_period_month = Column(String(20), nullable=True)
    primary_period_year = Column(SmallInteger, nullable=True)
    comparison_period_month = Column(String(20), nullable=True)
    comparison_period_year = Column(SmallInteger, nullable=True)
    scope_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    final_definition_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    narrative_snapshot_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    data_snapshot_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    validation_json = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    safe_error_message = Column(Text, nullable=True)
    integrity_identifier = Column(String(64), nullable=True, unique=True)
    generated_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("output_format IN ('excel', 'pdf', 'pptx')", name="ck_generated_report_format"),
        CheckConstraint("status IN ('ready', 'failed')", name="ck_generated_report_status"),
        Index("idx_generated_report_owner_created", "created_by_user_id", "created_at"),
        Index("idx_generated_report_period_type", "primary_period_year", "primary_period_month", "report_type"),
    )


class SavedReportTemplate(Base):
    __tablename__ = "saved_report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(180), nullable=False)
    report_type = Column(String(50), nullable=False)
    configuration = Column(JSON_COMPAT_TYPE, nullable=False, default=dict)
    included_sections = Column(JSON_COMPAT_TYPE, nullable=False, default=list)
    preferred_format = Column(String(20), nullable=False, default="pptx")
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    visibility = Column(String(20), nullable=False, default="private")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("preferred_format IN ('excel', 'pdf', 'pptx')", name="ck_saved_report_template_format"),
        CheckConstraint("visibility IN ('private')", name="ck_saved_report_template_visibility"),
        UniqueConstraint("owner_user_id", "name", name="uq_saved_report_template_owner_name"),
        Index("idx_saved_report_template_owner_updated", "owner_user_id", "updated_at"),
    )


# ============================================================
# 7. NOTIFICATIONS - MULTI-RECIPIENT
# ============================================================

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)  # data_upload, action_recorded, grade_alert, system, warning
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    room = Column(String(100), nullable=False)  # Socket.io room
    payload = Column(JSON_COMPAT_TYPE, nullable=True)
    link = Column(String(255), nullable=True)  # New column for navigation link
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    recipients = relationship("NotificationRecipient", back_populates="notification")


class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = Column(UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    notification = relationship("Notification", back_populates="recipients")
    user = relationship("User", back_populates="notifications")


# ============================================================
# 8. AUDIT LOG - COMPLETE CHANGE TRACKING
# ============================================================

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name = Column(String(100), nullable=False)
    operation = Column(String(50), nullable=False)  # INSERT, UPDATE, DELETE, SOFT_DELETE
    record_id = Column(UUID(as_uuid=True), nullable=True)
    old_values = Column(JSON_COMPAT_TYPE, nullable=True)
    new_values = Column(JSON_COMPAT_TYPE, nullable=True)
    performed_by_user_id = Column("performed_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(INET_COMPAT_TYPE, nullable=True)
    request_id = Column(String(100), nullable=True)

    # Relationships
    performed_by_user = relationship("User", back_populates="audit_logs")


# ============================================================
# 9. ONBOARDING STATE - TEAM SETUP TRACKING
# ============================================================

class OnboardingState(Base):
    __tablename__ = "onboarding_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False)
    current_step = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")  # pending, in_progress, completed, failed
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    team = relationship("Team")


class PerformanceRecordVersion(Base):
    __tablename__ = "performance_record_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_record_id = Column(UUID(as_uuid=True), nullable=False)
    original_record_year = Column(SmallInteger, nullable=False)
    version_number = Column(Integer, nullable=False)
    score = Column(Numeric(6, 2), nullable=False)
    grade = Column(String(5), nullable=False)
    status = Column(String(20), nullable=False)
    changed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    change_reason = Column(Text, nullable=True)

    # Relationships
    changed_by_user = relationship("User")

    __table_args__ = (
        ForeignKeyConstraint(
            ['original_record_id', 'original_record_year'],
            ['performance_records.id', 'performance_records.year'],
            ondelete="CASCADE"
        ),
        UniqueConstraint('original_record_id', 'version_number', name='uq_record_version'),
    )


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(100), nullable=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    error_class = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
