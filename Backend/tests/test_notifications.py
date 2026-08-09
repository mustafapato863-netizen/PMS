import pytest
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, User, Team, UserTeamAssignment, Notification, NotificationRecipient
from config.socket_config import save_notification_to_db

@pytest.fixture(scope="function")
def db_session():
    # Set up in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create only the required tables for notification testing
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        Team.__table__,
        UserTeamAssignment.__table__,
        Notification.__table__,
        NotificationRecipient.__table__
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    
    yield session
    session.close()

def test_admin_recipients_created_on_action_notifications(db_session):
    # 1. Create active Admin user
    admin = User(
        id=uuid.uuid4(),
        username="admin_test",
        email="admin@test.local",
        password_hash="mock_hash",
        role="Admin",
        is_active=True
    )
    db_session.add(admin)
    
    # 2. Create inactive Admin (should not receive notification)
    inactive_admin = User(
        id=uuid.uuid4(),
        username="inactive_admin",
        email="inactive@test.local",
        password_hash="mock_hash",
        role="Admin",
        is_active=False
    )
    db_session.add(inactive_admin)
    db_session.commit()
    
    # 3. Save notification
    notification_data = {
        'type': 'action',
        'message': 'Action Assigned to Employee A in Inbound',
        'team': 'Inbound'
    }
    
    db_id = save_notification_to_db(notification_data, db=db_session)
    assert db_id is not None
    
    # 4. Verify recipients in database
    recipients = db_session.query(NotificationRecipient).all()
    assert len(recipients) == 1
    assert recipients[0].user_id == admin.id

def test_admin_receives_notification_without_team_assignment(db_session):
    # Create Admin user (with no team assignment)
    admin = User(
        id=uuid.uuid4(),
        username="admin_unassigned",
        email="admin_unassigned@test.local",
        password_hash="mock_hash",
        role="Admin",
        is_active=True
    )
    db_session.add(admin)
    db_session.commit()
    
    # Save a team-scoped notification
    notification_data = {
        'type': 'action',
        'message': 'Action Assigned to Employee A in Sales',
        'team': 'Sales'
    }
    
    db_id = save_notification_to_db(notification_data, db=db_session)
    assert db_id is not None
    
    recipients = db_session.query(NotificationRecipient).filter(NotificationRecipient.user_id == admin.id).all()
    assert len(recipients) == 1

def test_manager_recipients_remain_team_scoped(db_session):
    # 1. Create a Team
    inbound_team = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", region="EGY", is_active=True)
    sales_team = Team(id=uuid.uuid4(), name="Sales", db_name="Sales", region="EGY", is_active=True)
    db_session.add_all([inbound_team, sales_team])
    db_session.flush()
    
    # 2. Create Managers
    inbound_manager = User(id=uuid.uuid4(), username="mgr_inbound", email="mgr1@test.local", password_hash="hash", role="Manager", is_active=True)
    sales_manager = User(id=uuid.uuid4(), username="mgr_sales", email="mgr2@test.local", password_hash="hash", role="Manager", is_active=True)
    db_session.add_all([inbound_manager, sales_manager])
    db_session.flush()
    
    # 3. Assign Managers to Teams
    db_session.add(UserTeamAssignment(id=uuid.uuid4(), user_id=inbound_manager.id, team_id=inbound_team.id, access_level="admin", assigned_by="Admin"))
    db_session.add(UserTeamAssignment(id=uuid.uuid4(), user_id=sales_manager.id, team_id=sales_team.id, access_level="admin", assigned_by="Admin"))
    db_session.commit()
    
    # 4. Save notification for Inbound team
    notification_data = {
        'type': 'action',
        'message': 'Action Assigned to Employee A in Inbound',
        'team': 'Inbound'
    }
    
    save_notification_to_db(notification_data, db=db_session)
    
    # Inbound manager should receive it, Sales manager should not
    inbound_recipients = db_session.query(NotificationRecipient).filter(NotificationRecipient.user_id == inbound_manager.id).all()
    sales_recipients = db_session.query(NotificationRecipient).filter(NotificationRecipient.user_id == sales_manager.id).all()
    
    assert len(inbound_recipients) == 1
    assert len(sales_recipients) == 0

def test_duplicate_recipients_are_not_created(db_session):
    # Create Team
    inbound_team = Team(id=uuid.uuid4(), name="Inbound", db_name="Inbound", region="EGY", is_active=True)
    db_session.add(inbound_team)
    db_session.flush()
    
    # Create Admin who is also assigned to Inbound team
    admin = User(
        id=uuid.uuid4(),
        username="admin_assigned",
        email="admin_assigned@test.local",
        password_hash="hash",
        role="Admin",
        is_active=True
    )
    db_session.add(admin)
    db_session.flush()
    
    db_session.add(UserTeamAssignment(id=uuid.uuid4(), user_id=admin.id, team_id=inbound_team.id, access_level="admin", assigned_by="Admin"))
    db_session.commit()
    
    notification_data = {
        'type': 'action',
        'message': 'Action Assigned in Inbound',
        'team': 'Inbound'
    }
    
    save_notification_to_db(notification_data, db=db_session)
    
    # Verify exactly 1 recipient is created for the Admin (no duplicate)
    recipients = db_session.query(NotificationRecipient).filter(NotificationRecipient.user_id == admin.id).all()
    assert len(recipients) == 1
