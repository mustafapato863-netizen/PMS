from config import settings
from config.socket_config import sio


def test_http_and_socket_origins_are_explicit():
    assert settings.CORS_ORIGINS
    assert "*" not in settings.CORS_ORIGINS
    assert tuple(sio.eio.cors_allowed_origins) == settings.CORS_ORIGINS
