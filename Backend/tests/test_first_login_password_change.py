"""Security lifecycle tests use an isolated database, never real user accounts."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.middleware.auth_middleware import AuthMiddleware
from api.routers.auth import router as auth_router
from api.routers.users_and_actions import users_router
from config.database import get_db
from models.models import Base, RefreshSession, User
from services.auth_service import AuthenticationService


@pytest.fixture()
def workspace():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    names = ['teams', 'employees', 'users', 'role_permissions', 'refresh_sessions',
             'user_team_assignments', 'user_function_assignments', 'user_region_assignments', 'user_branch_assignments']
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in names])
    with sessionmaker(bind=engine)() as db:
        app = FastAPI()
        app.add_middleware(AuthMiddleware)
        def database():
            yield db
        app.dependency_overrides[get_db] = database
        app.include_router(auth_router, prefix='/api')
        app.include_router(users_router, prefix='/api/users')
        @app.get('/api/protected')
        def protected():
            return {'success': True}
        with TestClient(app) as client:
            admin = AuthenticationService.create_user(db, 'admin', 'admin@test.local', 'AdminPassword123!', 'Admin')
            headers = {'Authorization': 'Bearer ' + AuthenticationService.authenticate_user(db, admin.username, 'AdminPassword123!')}
            created = client.post('/api/users/', headers=headers, json={
                'id': 'ignored', 'name': 'First Login', 'username': 'firstlogin',
                'password': 'TemporaryPassword123!', 'role': 'Performance Team',
                # A client may not disable the server-owned policy.
                'must_change_password': False,
            })
            assert created.status_code == 200
            yield db, client, created.json()['data']
    engine.dispose()


def login(client):
    result = client.post('/api/auth/login', json={'username': 'firstlogin', 'password': 'TemporaryPassword123!'}).json()['data']
    return result, {'Authorization': 'Bearer ' + result['access_token']}


def test_new_account_is_restricted_until_password_change(workspace):
    db, client, created = workspace
    assert created['must_change_password'] is True
    result, headers = login(client)
    assert result['must_change_password'] is True
    assert client.get('/api/auth/me', headers=headers).json()['data']['must_change_password'] is True
    for method, url in [('GET', '/api/protected'), ('GET', '/api/performance/catalog'), ('GET', '/api/users/'),
                        ('PUT', '/api/auth/profile'), ('POST', '/api/auth/presence/heartbeat')]:
        blocked = client.request(method, url, headers=headers, json={'full_name': 'Changed'})
        assert blocked.status_code == 403
        assert blocked.json()['code'] == 'PASSWORD_CHANGE_REQUIRED'
    refreshed = client.post('/api/auth/refresh', headers={'X-CSRF-Token': result['csrf_token']})
    assert refreshed.status_code == 200
    assert refreshed.json()['data']['must_change_password'] is True
    fresh_headers = {'Authorization': 'Bearer ' + refreshed.json()['data']['access_token']}
    assert client.get('/api/protected', headers=fresh_headers).status_code == 403


@pytest.mark.parametrize('current,new', [
    ('WrongPassword123!', 'PersonalPassword456!'),
    ('TemporaryPassword123!', 'TemporaryPassword123!'),
    ('TemporaryPassword123!', 'alllowercase123!'),
])
def test_failed_change_cannot_unlock_account(workspace, current, new):
    db, client, _ = workspace
    _, headers = login(client)
    user = db.query(User).filter_by(username='firstlogin').one()
    before = user.password_hash
    response = client.post('/api/auth/profile/password', headers=headers, json={'current_password': current, 'new_password': new})
    assert response.status_code == 400
    db.refresh(user)
    assert user.must_change_password is True
    assert user.password_hash == before
    assert client.get('/api/protected', headers=headers).status_code == 403


def test_successful_change_revokes_temporary_sessions_and_unlocks_new_login(workspace):
    db, client, _ = workspace
    _, headers = login(client)
    legacy = AuthenticationService.authenticate_user(db, 'firstlogin', 'TemporaryPassword123!')
    changed = client.post('/api/auth/profile/password', headers=headers, json={
        'current_password': 'TemporaryPassword123!', 'new_password': 'PersonalPassword456!',
    })
    assert changed.status_code == 200
    assert db.query(User).filter_by(username='firstlogin').one().must_change_password is False
    assert all(session.revoked_at is not None for session in db.query(RefreshSession).all())
    assert client.get('/api/protected', headers=headers).status_code == 401
    assert client.get('/api/protected', headers={'Authorization': 'Bearer ' + legacy}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'firstlogin', 'password': 'TemporaryPassword123!'}).status_code == 401
    result = client.post('/api/auth/login', json={'username': 'firstlogin', 'password': 'PersonalPassword456!'}).json()['data']
    assert result['must_change_password'] is False
    assert client.get('/api/protected', headers={'Authorization': 'Bearer ' + result['access_token']}).status_code == 200


def test_database_policy_cannot_be_bypassed_with_an_older_claim(workspace):
    db, client, _ = workspace
    user = db.query(User).filter_by(username='firstlogin').one()
    user.must_change_password = False
    db.commit()
    token = AuthenticationService.authenticate_user(db, user.username, 'TemporaryPassword123!')
    user.must_change_password = True
    db.commit()
    assert client.get('/api/protected', headers={'Authorization': 'Bearer ' + token}).status_code == 403


def test_pending_user_can_sign_out_without_clearing_the_policy(workspace):
    db, client, _ = workspace
    result, headers = login(client)
    response = client.post('/api/auth/logout', headers={**headers, 'X-CSRF-Token': result['csrf_token']})
    assert response.status_code == 200
    assert db.query(User).filter_by(username='firstlogin').one().must_change_password is True
    assert client.get('/api/protected', headers=headers).status_code == 401


def test_failure_revoking_sessions_rolls_back_the_entire_password_change(workspace, monkeypatch):
    db, client, _ = workspace
    _, headers = login(client)
    user = db.query(User).filter_by(username='firstlogin').one()
    before = user.password_hash
    def fail_revocation(*args, **kwargs):
        raise RuntimeError('Simulated session persistence failure')
    monkeypatch.setattr(AuthenticationService, 'revoke_all_sessions', fail_revocation)
    response = client.post('/api/auth/profile/password', headers=headers, json={
        'current_password': 'TemporaryPassword123!', 'new_password': 'PersonalPassword456!',
    })
    assert response.status_code == 500
    db.refresh(user)
    assert user.must_change_password is True
    assert user.password_hash == before
    assert client.get('/api/protected', headers=headers).status_code == 403


def test_password_policy_migration_preserves_existing_accounts_and_rolls_back():
    path = Path(__file__).parents[1] / 'migrations/versions/c8d3f6a1b205_require_first_login_password_change.py'
    spec = importlib.util.spec_from_file_location('password_policy_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY, password_hash TEXT NOT NULL)'))
        connection.execute(text("INSERT INTO users VALUES (1, 'existing_hash')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert connection.execute(text('SELECT must_change_password FROM users WHERE id=1')).scalar() == 0
        assert connection.execute(text('SELECT password_hash FROM users WHERE id=1')).scalar() == 'existing_hash'
        migration.downgrade()
        assert 'must_change_password' not in {c['name'] for c in inspect(connection).get_columns('users')}
        assert connection.execute(text('SELECT password_hash FROM users WHERE id=1')).scalar() == 'existing_hash'
    engine.dispose()
