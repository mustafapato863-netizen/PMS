"""
Data JSON to DB Migration Script
Migrates users, employees, performance records, and corrective actions from data/ JSON files to database.
"""

import sys
import json
import uuid
from pathlib import Path
from decimal import Decimal
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import SessionLocal
from models.models import Team, Employee, PerformanceRecord, KPIValue, Action, User
from services.password_service import hash_password
from utils.user_identity import humanize_username

def migrate():
    db = SessionLocal()
    try:
        # 1. Load and create users if they don't exist
        print("Migrating users...")
        users_file = Path("data/users.json")
        if users_file.exists():
            with open(users_file, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
            for u in users_data:
                existing = db.query(User).filter(User.username == u['username']).first()
                if not existing:
                    user = User(
                        id=uuid.uuid4(),
                        full_name=(u.get('name') or humanize_username(u['username'])).strip(),
                        username=u['username'],
                        email=f"{u['username']}@test.com",
                        password_hash=hash_password(u['password']),
                        role=u['role'],
                        is_active=True
                    )
                    db.add(user)
            db.commit()

        # 2. Load employees
        print("Migrating employees...")
        emp_file = Path("data/employees.json")
        if emp_file.exists():
            with open(emp_file, 'r', encoding='utf-8') as f:
                emp_data = json.load(f)
            
            # Map team names to team UUIDs
            teams = db.query(Team).all()
            team_map = {t.name: t.id for t in teams}
            
            # Keep track of migrated employee IDs to avoid duplicate rows
            inserted_emp_ids = set()
            
            for emp in emp_data:
                emp_id = emp['id']
                if emp_id in inserted_emp_ids:
                    continue
                    
                existing = db.query(Employee).filter(Employee.employee_id == emp_id).first()
                if not existing:
                    team_name = emp['team']
                    team_id = team_map.get(team_name)
                    if not team_id:
                        # try fallback
                        for k, v in team_map.items():
                            if k.lower() == team_name.lower():
                                team_id = v
                                break
                    if not team_id:
                        # Create team dynamically if it doesn't exist
                        db_name = team_name.replace(' ', '_').lower()
                        print(f"Creating team dynamically: {team_name}")
                        new_team = Team(
                            id=uuid.uuid4(),
                            name=team_name,
                            db_name=db_name,
                            region=emp.get('region', 'UAE'),
                            is_active=True
                        )
                        db.add(new_team)
                        db.flush()
                        team_id = new_team.id
                        team_map[team_name] = team_id
                        
                    is_active = emp['status'] == 'Active' or 'Active' in emp['status']
                    employee = Employee(
                        id=uuid.uuid4(),
                        employee_id=emp_id,
                        name=emp['name'],
                        team_id=team_id,
                        region=emp.get('region', 'UAE'),
                        is_active=is_active
                    )
                    db.add(employee)
                    inserted_emp_ids.add(emp_id)
            db.commit()

        # 3. Load performance records
        print("Migrating performance records...")
        perf_file = Path("data/performance_records.json")
        if perf_file.exists():
            with open(perf_file, 'r', encoding='utf-8') as f:
                perf_data = json.load(f)
            
            # Query maps for quick UUID lookup
            employees = db.query(Employee).all()
            emp_map = {e.employee_id: e.id for e in employees}
            
            teams = db.query(Team).all()
            team_map = {t.name: t.id for t in teams}
            
            for record_idx, r in enumerate(perf_data):
                # Identity
                identity = r.get('identity', {})
                ext_emp_id = identity.get('employee_id')
                # Try fallback from record root if not in identity
                if not ext_emp_id:
                    ext_emp_id = r.get('employee_id')
                if not ext_emp_id:
                    continue
                
                # Lookup employee UUID
                emp_uuid = emp_map.get(ext_emp_id)
                if not emp_uuid:
                    continue
                
                team_name = identity.get('team') or r.get('team')
                team_uuid = team_map.get(team_name)
                if not team_uuid:
                    for k, v in team_map.items():
                        if k.lower() == team_name.lower():
                            team_uuid = v
                            break
                if not team_uuid:
                    continue
                
                month = identity.get('month') or r.get('month')
                year = 2026 # Default year
                
                # Check if performance record already exists in database
                existing_perf = db.query(PerformanceRecord).filter(
                    (PerformanceRecord.employee_id == emp_uuid) &
                    (PerformanceRecord.month == month) &
                    (PerformanceRecord.year == year)
                ).first()
                
                if not existing_perf:
                    eval_data = r.get('evaluation', {})
                    import math
                    score_val = eval_data.get('score', 0)
                    if isinstance(score_val, str) and score_val.lower() == 'nan':
                        score = 0.0
                    else:
                        try:
                            score = float(score_val)
                            if math.isnan(score) or math.isinf(score):
                                score = 0.0
                        except (ValueError, TypeError):
                            score = 0.0

                    # Multiply by 100 if score is in 0-1 range
                    if score <= 1.0 and score > 0:
                        score = score * 100
                    
                    grade = eval_data.get('grade', 'E')
                    if len(grade) > 1:
                        if grade.startswith('Exceed') or grade.startswith('A'):
                            grade = 'A'
                        elif grade.startswith('Meet') or grade.startswith('B'):
                            grade = 'B'
                        elif grade.startswith('Avg') or grade.startswith('C'):
                            grade = 'C'
                        elif grade.startswith('Below') or grade.startswith('D'):
                            grade = 'D'
                        else:
                            grade = 'E'
                    
                    status = 'Meets'
                    if score >= 85:
                        status = 'Exceeds'
                    elif score < 70:
                        status = 'Below'
                        
                    perf_id = uuid.uuid4()
                    perf_record = PerformanceRecord(
                        id=perf_id,
                        employee_id=emp_uuid,
                        team_id=team_uuid,
                        month=month,
                        year=year,
                        score=Decimal(str(round(score, 2))),
                        grade=grade,
                        status=status,
                        uploaded_at=datetime.utcnow()
                    )
                    db.add(perf_record)
                    
                    # Migrate KPI values
                    actuals = r.get('actual', {})
                    achievements = r.get('achievement', {})
                    
                    # Get the KPI configs for this team
                    from models.models import TeamKPIConfig
                    kpi_configs = db.query(TeamKPIConfig).filter(TeamKPIConfig.team_id == team_uuid).all()
                    
                    for config in kpi_configs:
                        kpi_key = config.kpi_key
                        
                        actual_val = actuals.get(kpi_key.lower()) or actuals.get(kpi_key)
                        if actual_val is None:
                            actual_val = actuals.get('booking_rate') if 'book' in kpi_key.lower() else 0.0
                        
                        target_val = 1.0
                        achievement_ratio = achievements.get(kpi_key) or achievements.get(kpi_key.lower()) or 1.0
                        
                        kpi_value = KPIValue(
                            id=uuid.uuid4(),
                            record_id=perf_id,
                            record_year=year,
                            kpi_key=kpi_key,
                            actual_value=Decimal(str(actual_val or 0.0)),
                            target_value=Decimal(str(target_val)),
                            achievement_ratio=Decimal(str(achievement_ratio or 1.0)),
                            weight_applied=config.weight,
                            contribution=Decimal(str(float(achievement_ratio or 1.0) * float(config.weight) * 100))
                        )
                        db.add(kpi_value)
            db.commit()

        # 4. Load corrective actions
        print("Migrating corrective actions...")
        actions_file = Path("data/corrective_actions.json")
        if actions_file.exists():
            with open(actions_file, 'r', encoding='utf-8') as f:
                actions_data = json.load(f)
            
            employees = db.query(Employee).all()
            emp_map = {e.employee_id: e.id for e in employees}
            emp_team_map = {e.id: e.team_id for e in employees}
            
            admin_user = db.query(User).filter(User.role == 'Admin').first()
            admin_id = admin_user.id if admin_user else None
            
            for act in actions_data:
                ext_emp_id = act.get('employee_id')
                emp_uuid = emp_map.get(ext_emp_id)
                if not emp_uuid:
                    continue
                
                team_uuid = emp_team_map.get(emp_uuid)
                if not team_uuid:
                    continue
                
                month = act.get('month', 'January')
                year = 2026
                
                # Map action type
                a_type = act.get('action_type', 'Coaching')
                if a_type not in ['Training', 'Reward', 'PIP', 'Monitor', 'Coaching', 'Warning', 'Promotion']:
                    a_type = 'Coaching'
                
                existing = db.query(Action).filter(
                    (Action.employee_id == emp_uuid) &
                    (Action.month == month) &
                    (Action.action_type == a_type)
                ).first()
                
                if not existing:
                    action = Action(
                        id=uuid.uuid4(),
                        employee_id=emp_uuid,
                        team_id=team_uuid,
                        month=month,
                        year=year,
                        action_type=a_type,
                        action_text=act.get('action_text', ''),
                        root_cause_note=act.get('root_cause_note', ''),
                        status='Open',
                        created_by_user_id=admin_id,
                        created_at=datetime.utcnow()
                    )
                    db.add(action)
            db.commit()

        print("Success: All data successfully migrated from JSON to database!")
    except Exception as e:
        db.rollback()
        print(f"Error during migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
