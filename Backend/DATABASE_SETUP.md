# Database Setup & Connection Guide

**Status**: ✅ Ready to connect  
**Database**: PostgreSQL  
**ORM**: SQLAlchemy with async support  
**Migrations**: Alembic

---

## Quick Start (5 minutes)

### 1. Install Dependencies
```bash
cd Backend
pip install -r requirements.txt
```

### 2. Configure Database

**Edit `../DevOps/.env`**:
```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/PMS_Sys
```

**Options**:
- **Local PostgreSQL**: `postgresql://<user>:<password>@localhost:5432/<database_name>`
- **Docker PostgreSQL**: `postgresql://postgres:<password>@db:5432/<database_name>`
- **Cloud (AWS RDS)**: `postgresql://<user>:<password>@<your-rds-endpoint>:5432/<database_name>`

### 3. Create Database
```bash
# Using psql (PostgreSQL command line)
psql -U postgres -h localhost

# Inside psql:
CREATE DATABASE PMS_Sys;
\q
```

### 4. Run Migrations
```bash
cd Backend
alembic upgrade head
```

### 5. Start Backend
```bash
uvicorn app:app --reload --port 8000
```

---

## Architecture Overview

### Database Layer Structure

```
Backend/
├── config/
│   └── database.py ⭐ Database configuration & session management
├── models/
│   ├── models.py ⭐ SQLAlchemy ORM models (database tables)
│   └── schemas.py ⭐ Pydantic schemas (API validation)
├── repositories/        (To be created in Part 5)
│   └── team_repo.py    Repository layer for CRUD operations
├── migrations/         (Alembic migrations)
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── requirements.txt ⭐ Python dependencies
├── .env ⭐ Environment configuration
└── app.py ⭐ FastAPI application

⭐ = Already set up
```

---

## Database Models Included

### 1. **Team Model** (Configuration)
```python
class Team(Base):
    __tablename__ = "teams"
    
    - id: UUID (primary key)
    - name: Team identifier (unique)
    - db_name: Database name (unique)
    - region: Geographic region (UAE, EGY, etc.)
    - is_active: Boolean flag
    - created_at, updated_at: Timestamps
    - employees: Relationship to Employee table
```

**Relationships**: 
- 1 Team → Many Employees
- 1 Team → Many KPI Configs
- 1 Team → Many Performance Records

### 2. **TeamKPIConfig Model** (KPI Setup per Team)
```python
class TeamKPIConfig(Base):
    __tablename__ = "team_kpi_config"
    
    - id: UUID (primary key)
    - team_id: Foreign key to Team
    - kpi_key: KPI identifier (attendance, productivity, etc.)
    - weight: Numeric weight (0.0 - 1.0)
    - direction: "higher_better" or "lower_better"
    - unit: Measurement unit (%, hours, count, etc.)
    - color: Hex color code for UI
    - actual_col, target_col: Excel column mappings
```

### 3. **Employee Model** (Employee Records)
```python
class Employee(Base):
    __tablename__ = "employees"
    
    - id: UUID (primary key)
    - employee_id: Employee ID from Excel (unique)
    - name: Full name
    - team_id: Foreign key to Team
    - region: Geographic region
    - is_active: Boolean flag
    - performance_records: Relationship to PerformanceRecord
```

### 4. **PerformanceRecord Model** (Monthly Performance Data)
```python
class PerformanceRecord(Base):
    __tablename__ = "performance_records"
    
    - id: UUID (primary key)
    - year: Year (partition key)
    - employee_id: Foreign key to Employee
    - team_id: Foreign key to Team
    - month: Month identifier (Jan-2024, etc.)
    - score: Normalized performance score (0-100)
    - grade: Letter grade (A, B, C, D, E)
    - status: Performance status (Exceeds, Meets, Below)
    - upload_id: Reference to UploadLog
    - kpi_values: Relationship to KPIValue
```

### 5. **KPIValue Model** (Individual KPI Data)
```python
class KPIValue(Base):
    __tablename__ = "kpi_values"
    
    - id: UUID (primary key)
    - record_id: Foreign key to PerformanceRecord
    - kpi_key: KPI identifier
    - actual_value: Actual achieved value
    - target_value: Target to achieve
    - achievement_ratio: Actual / Target
    - weight_applied: Weight for this KPI
    - contribution: Contribution to overall score
```

### 6. **UploadLog Model** (File Upload Tracking)
```python
class UploadLog(Base):
    __tablename__ = "upload_log"
    
    - id: UUID (primary key)
    - team_id: Foreign key to Team
    - month, year: Period of upload
    - record_count: Number of records uploaded
    - uploaded_by_user_id: User who uploaded
    - status: Status (pending, success, failed)
    - error_message: Error details if failed
    - uploaded_at: Timestamp
```

---

## Current Configuration

### File: `Backend/config/database.py`

**What it does**:
1. Loads `.env` file from `DevOps/` directory
2. Creates SQLAlchemy async engine with connection pooling
3. Provides `SessionLocal` for database sessions
4. Exports `get_db()` dependency for FastAPI

**Key Settings**:
```python
pool_size=20              # Number of connections in pool
max_overflow=10           # Extra connections when pool full
pool_pre_ping=True        # Test connection before using
pool_recycle=1800         # Recycle connections after 30 min
```

### File: `DevOps/.env`

**Current**:
```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/PMS_Sys
```

**Change if needed** (for different setup):
```env
# Local development
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/pms_dev

# Docker
DATABASE_URL=postgresql://postgres:<password>@db:5432/pms_prod

# AWS RDS
DATABASE_URL=postgresql://<user>:<password>@<rds-endpoint>:5432/<database_name>
```

### File: `Backend/requirements.txt`

**Database Dependencies** (already included):
```
sqlalchemy[asyncio]==2.0.41      # ORM
asyncpg==0.30.0                  # PostgreSQL async driver
alembic==1.16.4                  # Migrations
psycopg2-binary==2.9.10          # PostgreSQL driver
greenlet==3.2.3                  # Async support
python-dotenv==1.0.0             # .env file support
```

---

## How to Connect Database

### Step 1: Install PostgreSQL

**Windows**:
```bash
# Using Chocolatey
choco install postgresql

# Or download: https://www.postgresql.org/download/windows/
```

**macOS**:
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Linux**:
```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### Step 2: Create Database & User

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE PMS_Sys;

# Create user (optional, use postgres if just testing)
CREATE USER pms_user WITH PASSWORD '<secure_password>';
GRANT ALL PRIVILEGES ON DATABASE PMS_Sys TO pms_user;

# Exit
\q
```

### Step 3: Update `.env`

```env
DATABASE_URL=postgresql://pms_user:<secure_password>@localhost:5432/PMS_Sys
```

### Step 4: Install Python Dependencies

```bash
cd Backend
pip install -r requirements.txt
```

### Step 5: Run Migrations

```bash
# Initialize Alembic (if not already done)
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Initial schema"

# Apply migration
alembic upgrade head
```

### Step 6: Verify Connection

```bash
python -c "
from config.database import engine, SessionLocal
from models.models import Base

# Test connection
with engine.connect() as conn:
    result = conn.execute('SELECT 1')
    print('✓ Database connected successfully')

# Create tables
Base.metadata.create_all(bind=engine)
print('✓ Tables created')
"
```

### Step 7: Start Backend

```bash
uvicorn app:app --reload --port 8000
```

---

## Integration with Existing Code

### How Models are Used in Services

**Example: Team Service** (to be updated):

**Before** (JSON-based):
```python
def get_all_teams():
    teams_config = load_teams_config()  # Read from JSON
    return list(teams_config.values())
```

**After** (Database-based):
```python
from config.database import SessionLocal
from models.models import Team

def get_all_teams():
    db = SessionLocal()
    teams = db.query(Team).filter(Team.is_active == True).all()
    db.close()
    return teams
```

### Example: Using Sessions in FastAPI

```python
from fastapi import Depends
from config.database import get_db
from models.models import Team

@app.get("/api/teams")
async def list_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    return teams
```

---

## Common Tasks

### Create New Team

```python
from config.database import SessionLocal
from models.models import Team
import uuid

db = SessionLocal()
team = Team(
    id=uuid.uuid4(),
    name="inbound",
    db_name="inbound_db",
    region="UAE",
    is_active=True
)
db.add(team)
db.commit()
db.close()
```

### Query Teams

```python
db = SessionLocal()

# Get all active teams
teams = db.query(Team).filter(Team.is_active == True).all()

# Get specific team
team = db.query(Team).filter(Team.name == "inbound").first()

# Count teams
count = db.query(Team).count()

db.close()
```

### Update Team

```python
db = SessionLocal()
team = db.query(Team).filter(Team.name == "inbound").first()
team.region = "EGY"
db.commit()
db.close()
```

### Delete Team (Soft Delete)

```python
db = SessionLocal()
team = db.query(Team).filter(Team.name == "inbound").first()
team.is_active = False
db.commit()
db.close()
```

---

## Async Database Operations

### Using Async with FastAPI

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# For async operations (recommended):
DATABASE_URL = "postgresql+asyncpg://<user>:<password>@localhost/<dbname>"

@app.get("/api/teams")
async def list_teams(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team))
    teams = result.scalars().all()
    return teams
```

**Note**: Current setup uses synchronous SQLAlchemy. To enable async:
1. Update `database.py` to use `create_async_engine()`
2. Update models to use `asyncio-compatible` relationships
3. Change dependencies to use `AsyncSession`

---

## Troubleshooting

### Error: "DATABASE_URL is not set"
- **Solution**: Verify `.env` file exists in `DevOps/` directory
- Check: `cat DevOps/.env` (should show DATABASE_URL)

### Error: "could not connect to server"
- **Solution**: Verify PostgreSQL is running
  ```bash
  # macOS
  brew services list | grep postgresql
  
  # Linux
  sudo systemctl status postgresql
  
  # Windows
  # Check Services app or: net start postgresql-x64-15
  ```

### Error: "FATAL: database does not exist"
- **Solution**: Create database
  ```bash
  psql -U postgres -c "CREATE DATABASE PMS_Sys;"
  ```

### Error: "could not translate host name to address"
- **Solution**: Verify localhost connection
  - Use `127.0.0.1` instead of `localhost`
  - Or verify PostgreSQL network settings

### Connection Timeout
- **Solution**: Check firewall and PostgreSQL port (default: 5432)
  ```bash
  netstat -an | grep 5432  # Linux/macOS
  netstat -ano | findstr :5432  # Windows
  ```

---

## Next Steps

### 1. Update Team Service to Use Database

Replace JSON file reading with database queries:
```bash
# Files to update:
Backend/services/team_service.py          # Use db instead of JSON
Backend/api/routers/team_management.py    # Already compatible
```

### 2. Create Repository Layer

Add repository pattern for CRUD operations:
```
Backend/repositories/
├── team_repo.py
├── employee_repo.py
├── performance_repo.py
└── base_repo.py
```

### 3. Add Authentication

Link user_id to uploads and changes:
```python
class User(Base):
    __tablename__ = "users"
    id = Column(UUID, primary_key=True)
    username = Column(String, unique=True)
    ...
```

### 4. Run Tests

Verify database integration:
```bash
pytest tests/test_database.py
pytest tests/test_services.py
```

---

## Database Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      DATABASE SCHEMA                         │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐
│    Teams     │◄─────┐
└──────────────┘      │
      │                │
      │ (1:N)         │ (FK)
      │                │
      ├─────────────────►┌─────────────────┐
      │                │  TeamKPIConfig   │
      │                └─────────────────┘
      │
      ├────────────────►┌─────────────────┐
      │ (1:N)          │   Employees     │
      │                └─────────────────┘
      │                      │
      │                      │ (1:N)
      │                      │
      │                      ├──────┐
      │                      │      │
      ▼                      ▼      ▼
┌──────────────────┐    ┌──────────────────────┐
│   UploadLog      │◄───│ PerformanceRecords   │
└──────────────────┘    └──────────────────────┘
                               │
                               │ (1:N)
                               │
                               ▼
                        ┌──────────────────┐
                        │    KPIValues     │
                        └──────────────────┘
```

---

## Summary

✅ **Database is configured and ready**  
✅ **Models are defined**  
✅ **Connection settings in `.env`**  
✅ **Dependencies installed in `requirements.txt`**  

**Next**: Create migrations and update services to use database instead of JSON files.

For support: Check `PHASE-5-PART-5-PLAN.md` for detailed implementation guide.

