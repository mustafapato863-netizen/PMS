import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.models import Base, Employee, Team, User
from services.user_identity_service import UserIdentityService


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Team.__table__, Employee.__table__, User.__table__],
    )
    return sessionmaker(bind=engine)()


def _user(*, username: str, employee_id: str | None = None, full_name: str = "") -> User:
    return User(
        id=uuid.uuid4(),
        employee_id=employee_id,
        full_name=full_name,
        username=username,
        email=f"{username}@test.local",
        password_hash="not-used",
        role="Manager",
        is_active=True,
        failed_login_attempts=0,
    )


def test_display_name_uses_linked_employee_full_name():
    db = _db()
    team = Team(
        id=uuid.uuid4(),
        name="Test Team",
        db_name="Test Team",
        region="UAE",
    )
    user = _user(username="dr_ahmed_essa", employee_id="EMP-1")
    db.add_all([
        team,
        Employee(
            id=uuid.uuid4(),
            employee_id="EMP-1",
            name="Dr. Ahmed Mohamed Essa",
            team_id=team.id,
            region="UAE",
        ),
        user,
    ])
    db.commit()

    assert UserIdentityService.display_name(db, user) == "Dr. Ahmed Mohamed Essa"
    db.close()


def test_display_name_prefers_independent_user_full_name():
    db = _db()
    user = _user(username="dr_ahmed_essa", full_name="Ahmed Essa")
    db.add(user)
    db.commit()

    assert UserIdentityService.display_name(db, user) == "Ahmed Essa"
    db.close()


def test_display_name_humanizes_login_username_when_employee_is_not_linked():
    db = _db()
    user = _user(username="dr_ahmed_essa")
    db.add(user)
    db.commit()

    assert UserIdentityService.display_name(db, user) == "Dr Ahmed Essa"
    db.close()
