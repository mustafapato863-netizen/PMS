from unittest.mock import Mock
import uuid

import pytest

from models.models import User
from services.user_profile_service import UserProfileService


def test_profile_update_rolls_back_when_commit_fails():
    db = Mock()
    db.commit.side_effect = RuntimeError("database unavailable")
    user = User(
        id=uuid.uuid4(),
        username="profile_user",
        email="profile@test.com",
        full_name="Original Name",
        password_hash="not-used",
        role="Viewer",
    )
    service = UserProfileService(db)
    service.users = Mock()
    service.users.set_full_name.return_value = user

    with pytest.raises(RuntimeError, match="database unavailable"):
        service.update_full_name(str(user.id), "Updated Name")

    db.rollback.assert_called_once_with()
