-- ============================================================
-- PMS DATABASE SCHEMA - PRODUCTION READY
-- Version: 3.0 (Comprehensive & Fully Validated)
-- Date: June 20, 2026
-- ============================================================

-- ============================================================
-- SECTION 1: EXTENSIONS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- SECTION 2: ENUM TYPES
-- ============================================================

-- Authentication & Authorization
CREATE TYPE user_role AS ENUM ('Admin', 'Manager', 'Executive', 'Viewer');
CREATE TYPE access_level AS ENUM ('read', 'write', 'admin');

-- KPI Configuration
CREATE TYPE kpi_direction AS ENUM ('higher_better', 'lower_better');
CREATE TYPE kpi_unit AS ENUM ('%', 'currency', 'number', 'min');

-- Performance
CREATE TYPE grade_class AS ENUM ('A', 'B', 'C', 'D', 'E');
CREATE TYPE perf_status AS ENUM ('Exceeds', 'Meets', 'Below');

-- Actions
CREATE TYPE action_type AS ENUM ('Training', 'Reward', 'PIP', 'Monitor', 'Coaching', 'Warning', 'Promotion');
CREATE TYPE action_status AS ENUM ('Open', 'In Progress', 'Completed', 'Cancelled');

-- Uploads
CREATE TYPE upload_status AS ENUM ('pending', 'processing', 'success', 'failed');

-- Notifications
CREATE TYPE notif_type AS ENUM ('data_upload', 'action_recorded', 'grade_alert', 'system', 'warning');

-- Audit
CREATE TYPE audit_op AS ENUM ('INSERT', 'UPDATE', 'DELETE', 'SOFT_DELETE');

-- ============================================================
-- SECTION 3: CONFIGURATION TABLES
-- ============================================================

-- Teams - core organizational unit
CREATE TABLE teams (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name        VARCHAR(100) NOT NULL,
  db_name     VARCHAR(100) NOT NULL,
  region      VARCHAR(10)  NOT NULL DEFAULT 'UAE',
  is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_teams_db_name UNIQUE (db_name),
  CONSTRAINT uq_teams_name    UNIQUE (name)
);

-- KPI Configuration per team
CREATE TABLE team_kpi_config (
  id                UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id           UUID          NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  kpi_key           VARCHAR(50)   NOT NULL,
  kpi_label         VARCHAR(100)  NOT NULL,
  weight            NUMERIC(5,4)  NOT NULL,
  direction         kpi_direction NOT NULL DEFAULT 'higher_better',
  unit              kpi_unit      NOT NULL DEFAULT '%',
  color             VARCHAR(20)   NOT NULL DEFAULT '#10B981',
  actual_col        VARCHAR(100)  NOT NULL,
  target_col        VARCHAR(100)  NOT NULL,
  achievement_col   VARCHAR(100),
  volume_unit       VARCHAR(20),
  display_order     SMALLINT      NOT NULL DEFAULT 0,
  performance_level VARCHAR(20)   NOT NULL DEFAULT 'Employee',
  created_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_by        VARCHAR(100),

  CONSTRAINT uq_kpi_team_level_key UNIQUE (team_id, performance_level, kpi_key),
  CONSTRAINT chk_kpi_weight        CHECK (weight > 0 AND weight <= 1.0),
  CONSTRAINT ck_team_kpi_performance_level CHECK (performance_level IN ('Employee', 'Managerial', 'Corporate'))
);

-- KPI Weight History - tracks changes for historical accuracy
CREATE TABLE kpi_weight_history (
  id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id     UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  kpi_key     VARCHAR(50)  NOT NULL,
  old_weight  NUMERIC(5,4) NOT NULL,
  new_weight  NUMERIC(5,4) NOT NULL,
  changed_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  changed_by  VARCHAR(100) NOT NULL,
  reason      TEXT
);

-- Grade Thresholds per team - determines A/B/C/D/E
CREATE TABLE grade_thresholds (
  id          UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id     UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  grade_a     NUMERIC(5,2) NOT NULL DEFAULT 95,
  grade_b     NUMERIC(5,2) NOT NULL DEFAULT 90,
  grade_c     NUMERIC(5,2) NOT NULL DEFAULT 80,
  grade_d     NUMERIC(5,2) NOT NULL DEFAULT 70,
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_by  VARCHAR(100),

  CONSTRAINT uq_grade_team   UNIQUE (team_id),
  CONSTRAINT chk_threshold_order
    CHECK (grade_a > grade_b AND grade_b > grade_c AND grade_c > grade_d AND grade_d > 0)
);

-- ============================================================
-- SECTION 4: EMPLOYEES
-- ============================================================

CREATE TABLE employees (
  id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  employee_id       VARCHAR(50)  NOT NULL,
  name              VARCHAR(255) NOT NULL,
  team_id           UUID         NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  region            VARCHAR(10)  NOT NULL DEFAULT 'UAE',
  is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
  performance_level VARCHAR(20)  NOT NULL DEFAULT 'Employee',
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_employees_external_id UNIQUE (employee_id),
  CONSTRAINT ck_employee_performance_level CHECK (performance_level IN ('Employee', 'Managerial', 'Corporate'))
);

-- ============================================================
-- SECTION 5: AUTHENTICATION & AUTHORIZATION TABLES
-- ============================================================

-- Users table
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  employee_id     VARCHAR(50)  REFERENCES employees(employee_id) ON DELETE SET NULL,
  username        VARCHAR(100) NOT NULL,
  email           VARCHAR(255) NOT NULL,
  password_hash   TEXT         NOT NULL,
  role            user_role    NOT NULL DEFAULT 'Viewer',
  is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
  last_login      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_users_username UNIQUE (username),
  CONSTRAINT uq_users_email    UNIQUE (email)
);

-- User-Team assignments - scopes managers to specific teams
CREATE TABLE user_team_assignments (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id           UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  team_id           UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  performance_level VARCHAR(20),
  access_level      access_level NOT NULL DEFAULT 'read',
  assigned_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  assigned_by       VARCHAR(100) NOT NULL,

  CONSTRAINT uq_user_team_level UNIQUE (user_id, team_id, performance_level),
  CONSTRAINT ck_user_team_assignment_performance_level CHECK (performance_level IS NULL OR performance_level IN ('Employee', 'Managerial', 'Corporate'))
);

-- ============================================================
-- SECTION 6: UPLOADS - Track data ingestion
-- ============================================================

CREATE TABLE upload_log (
  id                  UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
  team_id             UUID          NOT NULL REFERENCES teams(id) ON DELETE RESTRICT,
  month               VARCHAR(20)   NOT NULL,
  year                SMALLINT      NOT NULL,
  record_count        INTEGER       NOT NULL DEFAULT 0,
  uploaded_by_user_id UUID          REFERENCES users(id) ON DELETE SET NULL,
  status              upload_status NOT NULL DEFAULT 'pending',
  error_message       TEXT,
  uploaded_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_upload_team_month_year UNIQUE (team_id, month, year),
  CONSTRAINT chk_upload_year CHECK (year >= 2020 AND year <= 2100)
);

-- ============================================================
-- SECTION 7: PERFORMANCE RECORDS (PARTITIONED BY YEAR)
-- ============================================================

-- Main partitioned table
CREATE TABLE performance_records (
  id                UUID         NOT NULL DEFAULT uuid_generate_v4(),
  employee_id       UUID         NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
  team_id           UUID         NOT NULL REFERENCES teams(id)     ON DELETE RESTRICT,
  month             VARCHAR(20)  NOT NULL,
  year              SMALLINT     NOT NULL,
  score             NUMERIC(6,2) NOT NULL,
  grade             grade_class  NOT NULL,
  status            perf_status  NOT NULL,
  upload_id         UUID         REFERENCES upload_log(id) ON DELETE SET NULL,
  uploaded_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  performance_level VARCHAR(20)  NOT NULL DEFAULT 'Employee',

  CONSTRAINT pk_performance_records PRIMARY KEY (id, year),
  CONSTRAINT uq_perf_employee_month_year UNIQUE (employee_id, month, year),
  CONSTRAINT chk_score_range CHECK (score >= 0 AND score <= 100),
  CONSTRAINT chk_perf_year   CHECK (year >= 2020 AND year <= 2100),
  CONSTRAINT ck_performance_record_level CHECK (performance_level IN ('Employee', 'Managerial', 'Corporate'))
) PARTITION BY RANGE (year);

-- Create partitions for current and future years
DO $$
DECLARE
  start_year INTEGER := 2020;
  end_year INTEGER := 2030;
  current_year INTEGER;
BEGIN
  FOR current_year IN start_year..end_year LOOP
    EXECUTE format('
      CREATE TABLE IF NOT EXISTS performance_records_%s
      PARTITION OF performance_records
      FOR VALUES FROM (%s) TO (%s)
    ', current_year, current_year, current_year + 1);
  END LOOP;

  -- Default partition for out-of-range years
  CREATE TABLE IF NOT EXISTS performance_records_default
    PARTITION OF performance_records DEFAULT;
END $$;

-- KPI Values - detailed breakdown per performance record
CREATE TABLE kpi_values (
  id                UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
  record_id         UUID         NOT NULL,
  record_year       SMALLINT     NOT NULL,
  kpi_key           VARCHAR(50)  NOT NULL,
  actual_value      NUMERIC(18,4) NOT NULL,
  target_value      NUMERIC(18,4) NOT NULL,
  achievement_ratio NUMERIC(10,4) NOT NULL,
  weight_applied    NUMERIC(5,4)  NOT NULL,  
  contribution      NUMERIC(6,2)  NOT NULL,

  CONSTRAINT fk_kpi_values_performance_records 
    FOREIGN KEY (record_id, record_year) REFERENCES performance_records(id, year) ON DELETE CASCADE,
  CONSTRAINT uq_kpi_value_record_key  UNIQUE (record_id, kpi_key),
  CONSTRAINT chk_achievement_positive CHECK (achievement_ratio >= 0),
  CONSTRAINT chk_contribution_range   CHECK (contribution >= 0 AND contribution <= 100)
);

-- ============================================================
-- SECTION 8: ACTIONS - Manager interventions
-- ============================================================

CREATE TABLE actions (
  id                  UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
  employee_id         UUID          NOT NULL REFERENCES employees(id)  ON DELETE RESTRICT,
  team_id             UUID          NOT NULL REFERENCES teams(id)      ON DELETE RESTRICT,
  month               VARCHAR(20)   NOT NULL,
  year                SMALLINT      NOT NULL,
  action_type         action_type   NOT NULL,
  action_text         TEXT          NOT NULL,
  root_cause_note     TEXT,
  status              action_status NOT NULL DEFAULT 'Open',
  created_by_user_id  UUID          REFERENCES users(id) ON DELETE SET NULL,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_by_user_id  UUID          REFERENCES users(id) ON DELETE SET NULL,
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_action_year CHECK (year >= 2020 AND year <= 2100)
);

-- ============================================================
-- SECTION 9: NOTIFICATIONS (Multi-recipient)
-- ============================================================

-- Notification master record
CREATE TABLE notifications (
  id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
  type        notif_type  NOT NULL,
  title       VARCHAR(255) NOT NULL,
  message     TEXT         NOT NULL,
  room        VARCHAR(100) NOT NULL,
  payload     JSONB,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Recipient junction table
CREATE TABLE notification_recipients (
  id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
  notification_id UUID        NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
  user_id         UUID        NOT NULL REFERENCES users(id)         ON DELETE CASCADE,
  is_read         BOOLEAN     NOT NULL DEFAULT FALSE,
  read_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_notif_recipient UNIQUE (notification_id, user_id)
);

-- ============================================================
-- SECTION 10: AUDIT LOG - Complete change tracking
-- ============================================================

CREATE TABLE audit_log (
  id           UUID      PRIMARY KEY DEFAULT uuid_generate_v4(),
  table_name   VARCHAR(100) NOT NULL,
  operation    audit_op     NOT NULL,
  record_id    UUID,
  old_values   JSONB,
  new_values   JSONB,
  performed_by UUID          REFERENCES users(id) ON DELETE SET NULL,
  performed_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  ip_address   INET
);

-- ============================================================
-- SECTION 11: INDEXES - Performance Optimization
-- ============================================================

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_employee_id ON users(employee_id);
CREATE INDEX idx_employees_team_id      ON employees(team_id);
CREATE INDEX idx_employees_name_trgm    ON employees USING gin(name gin_trgm_ops);
CREATE INDEX idx_employees_external_id  ON employees(employee_id);
CREATE INDEX idx_perf_team_month_year   ON performance_records(team_id, year, month);
CREATE INDEX idx_perf_employee_id       ON performance_records(employee_id);
CREATE INDEX idx_perf_employee_year     ON performance_records(employee_id, year);
CREATE INDEX idx_perf_grade             ON performance_records(grade, year, month);
CREATE INDEX idx_perf_score_desc        ON performance_records(team_id, score DESC);
CREATE INDEX idx_kpi_values_record_id   ON kpi_values(record_id);
CREATE INDEX idx_kpi_under              ON kpi_values(kpi_key, achievement_ratio) WHERE achievement_ratio < 1.0;
CREATE INDEX idx_actions_employee_id    ON actions(employee_id);
CREATE INDEX idx_actions_team_month     ON actions(team_id, year, month);
CREATE INDEX idx_actions_created_at     ON actions(created_at DESC);
CREATE INDEX idx_actions_status         ON actions(status) WHERE status != 'Completed';
CREATE INDEX idx_upload_team_month_year ON upload_log(team_id, month, year);
CREATE INDEX idx_upload_created_at      ON upload_log(uploaded_at DESC);
CREATE INDEX idx_upload_status          ON upload_log(status) WHERE status = 'pending';
CREATE INDEX idx_notif_recipients_unread ON notification_recipients(user_id, is_read) WHERE is_read = FALSE;
CREATE INDEX idx_notif_recipients_recent ON notification_recipients(user_id, created_at DESC);
CREATE INDEX idx_notif_recipients_notif  ON notification_recipients(notification_id);
CREATE INDEX idx_audit_table_record     ON audit_log(table_name, record_id);
CREATE INDEX idx_audit_performed_at     ON audit_log(performed_at DESC);
CREATE INDEX idx_audit_performed_by     ON audit_log(performed_by);
CREATE INDEX idx_user_team_user_id      ON user_team_assignments(user_id);
CREATE INDEX idx_user_team_team_id      ON user_team_assignments(team_id);

-- ============================================================
-- SECTION 12: TRIGGERS & FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_teams_updated_at BEFORE UPDATE ON teams FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_employees_updated_at BEFORE UPDATE ON employees FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_team_kpi_updated_at BEFORE UPDATE ON team_kpi_config FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION check_kpi_weights_sum()
RETURNS TRIGGER AS $$
DECLARE
  total NUMERIC;
BEGIN
  SELECT ROUND(SUM(weight)::numeric, 4) INTO total FROM team_kpi_config WHERE team_id = NEW.team_id;
  IF total > 1.0001 THEN
    RAISE EXCEPTION 'KPI weights for team % sum to %, must equal 1.0', NEW.team_id, total;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_kpi_weight_sum AFTER INSERT OR UPDATE ON team_kpi_config FOR EACH ROW EXECUTE FUNCTION check_kpi_weights_sum();

CREATE OR REPLACE FUNCTION write_audit_log()
RETURNS TRIGGER AS $$
DECLARE
  old_json JSONB;
  new_json JSONB;
  record_id_value UUID;
BEGIN
  IF TG_TABLE_NAME IN ('users', 'teams', 'employees', 'team_kpi_config', 'grade_thresholds', 'performance_records') THEN
    record_id_value := COALESCE(NEW.id, OLD.id);
  ELSE
    record_id_value := NULL;
  END IF;

  IF TG_OP != 'INSERT' THEN old_json := row_to_json(OLD)::jsonb; END IF;
  IF TG_OP != 'DELETE' THEN new_json := row_to_json(NEW)::jsonb; END IF;

  INSERT INTO audit_log(table_name, operation, record_id, old_values, new_values)
  VALUES (TG_TABLE_NAME, TG_OP::audit_op, record_id_value, old_json, new_json);
  RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_users AFTER INSERT OR UPDATE OR DELETE ON users FOR EACH ROW EXECUTE FUNCTION write_audit_log();
CREATE TRIGGER trg_audit_teams AFTER INSERT OR UPDATE OR DELETE ON teams FOR EACH ROW EXECUTE FUNCTION write_audit_log();
CREATE TRIGGER trg_audit_employees AFTER INSERT OR UPDATE OR DELETE ON employees FOR EACH ROW EXECUTE FUNCTION write_audit_log();
CREATE TRIGGER trg_audit_grade_thresholds AFTER INSERT OR UPDATE OR DELETE ON grade_thresholds FOR EACH ROW EXECUTE FUNCTION write_audit_log();
CREATE TRIGGER trg_audit_team_kpi_config AFTER INSERT OR UPDATE OR DELETE ON team_kpi_config FOR EACH ROW EXECUTE FUNCTION write_audit_log();
CREATE TRIGGER trg_audit_performance_records AFTER INSERT OR UPDATE OR DELETE ON performance_records FOR EACH ROW EXECUTE FUNCTION write_audit_log();
CREATE TRIGGER trg_audit_actions AFTER INSERT OR UPDATE OR DELETE ON actions FOR EACH ROW EXECUTE FUNCTION write_audit_log();

-- ============================================================
-- SECTION 13: MATERIALIZED VIEWS - FIXED
-- ============================================================

CREATE MATERIALIZED VIEW mv_team_monthly_summary AS
SELECT
  t.id           AS team_id,
  t.name         AS team_name,
  pr.year,
  pr.month,
  COUNT(pr.id)                                          AS employee_count,
  ROUND(AVG(pr.score)::numeric, 2)                      AS avg_score,
  ROUND(MAX(pr.score)::numeric, 2)                      AS max_score,
  ROUND(MIN(pr.score)::numeric, 2)                      AS min_score,
  COUNT(CASE WHEN pr.grade = 'A' THEN 1 END)            AS grade_a_count,
  COUNT(CASE WHEN pr.grade = 'B' THEN 1 END)            AS grade_b_count,
  COUNT(CASE WHEN pr.grade = 'C' THEN 1 END)            AS grade_c_count,
  COUNT(CASE WHEN pr.grade = 'D' THEN 1 END)            AS grade_d_count,
  COUNT(CASE WHEN pr.grade = 'E' THEN 1 END)            AS grade_e_count,
  COUNT(CASE WHEN pr.status = 'Exceeds' THEN 1 END)     AS exceeds_count,
  COUNT(CASE WHEN pr.status = 'Below'   THEN 1 END)     AS below_count,
  ROUND(AVG(kv.achievement_ratio)::numeric, 2)          AS avg_achievement_ratio
FROM performance_records pr
JOIN teams t ON t.id = pr.team_id
LEFT JOIN kpi_values kv ON kv.record_id = pr.id
GROUP BY t.id, t.name, pr.year, pr.month;

CREATE UNIQUE INDEX ON mv_team_monthly_summary(team_id, year, month);

-- ============================================================
-- SECTION 14: INITIAL SEED DATA
-- ============================================================

INSERT INTO users (username, email, password_hash, role) VALUES
  ('admin', 'admin@pms.local', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8XJ7Z7j6zK8X5qV5Lpq', 'Admin')
ON CONFLICT (username) DO NOTHING;

-- ============================================================
-- SECTION 15: MAINTENANCE FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION create_performance_partitions(start_year INTEGER DEFAULT 2020, end_year INTEGER DEFAULT 2035)
RETURNS VOID AS $$
DECLARE year_val INTEGER;
BEGIN
  FOR year_val IN start_year..end_year LOOP
    EXECUTE format('CREATE TABLE IF NOT EXISTS performance_records_%s PARTITION OF performance_records FOR VALUES FROM (%s) TO (%s)', year_val, year_val, year_val + 1);
  END LOOP;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION refresh_dashboard_views() RETURNS VOID AS $$
BEGIN REFRESH MATERIALIZED VIEW CONCURRENTLY mv_team_monthly_summary; END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION calculate_grade(p_score NUMERIC, p_team_id UUID)
RETURNS grade_class AS $$
DECLARE thresholds RECORD;
BEGIN
  SELECT grade_a, grade_b, grade_c, grade_d INTO thresholds FROM grade_thresholds WHERE team_id = p_team_id;
  IF NOT FOUND THEN
    RETURN CASE
      WHEN p_score >= 95 THEN 'A'::grade_class WHEN p_score >= 90 THEN 'B'::grade_class
      WHEN p_score >= 80 THEN 'C'::grade_class WHEN p_score >= 70 THEN 'D'::grade_class ELSE 'E'::grade_class
    END;
  END IF;
  RETURN CASE
    WHEN p_score >= thresholds.grade_a THEN 'A'::grade_class WHEN p_score >= thresholds.grade_b THEN 'B'::grade_class
    WHEN p_score >= thresholds.grade_c THEN 'C'::grade_class WHEN p_score >= thresholds.grade_d THEN 'D'::grade_class ELSE 'E'::grade_class
  END;
END; $$ LANGUAGE plpgsql;

-- ============================================================
-- SECTION 16: SECURITY POLICIES (Row Level Security)
-- ============================================================

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE actions ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_self ON users FOR SELECT USING (id = current_setting('app.current_user_id', true)::UUID);
CREATE POLICY managers_view_employees ON employees FOR SELECT USING (EXISTS (SELECT 1 FROM user_team_assignments uta WHERE uta.user_id = current_setting('app.current_user_id', true)::UUID AND uta.team_id = employees.team_id AND uta.access_level IN ('read', 'write', 'admin')));
CREATE POLICY managers_view_performance ON performance_records FOR SELECT USING (EXISTS (SELECT 1 FROM user_team_assignments uta WHERE uta.user_id = current_setting('app.current_user_id', true)::UUID AND uta.team_id = performance_records.team_id));

-- ============================================================
-- END OF SCHEMA
-- ============================================================
SELECT version();