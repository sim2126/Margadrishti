from __future__ import annotations

from importlib import resources

import pytest


def test_production_mode_requires_postgis_read_dsn(monkeypatch):
    from margadrishti.api.deps import get_repository, get_service
    from margadrishti.core.config import get_settings

    monkeypatch.setenv("MARGA_OFFLINE", "false")
    monkeypatch.setenv("POSTGIS_DSN", "")
    monkeypatch.setenv("POSTGIS_READ_DSN", "")
    get_settings.cache_clear()
    get_service.cache_clear()

    with pytest.raises(RuntimeError, match="POSTGIS_READ_DSN"):
        get_repository()


def test_schema_does_not_hardcode_api_role_password():
    sql = (resources.files("margadrishti.db") / "schema.sql").read_text(encoding="utf-8")
    assert "PASSWORD 'margadrishti_api'" not in sql
    assert "CREATE ROLE margadrishti_api LOGIN" in sql


def test_runtime_secrets_apply_api_role_password(monkeypatch):
    from margadrishti.core.config import get_settings
    from margadrishti.db.serving import _apply_runtime_secrets

    class FakeConn:
        def __init__(self) -> None:
            self.calls = []

        def execute(self, stmt, params=None):
            self.calls.append((str(stmt), params))

    monkeypatch.setenv("MARGA_API_PASSWORD", "unit-test-secret")
    get_settings.cache_clear()
    conn = FakeConn()
    _apply_runtime_secrets(conn, get_settings())

    assert conn.calls
    assert "ALTER ROLE margadrishti_api" in conn.calls[0][0]
    assert conn.calls[0][1] == {"password": "unit-test-secret"}


def test_runtime_secrets_reject_blank_api_role_password(monkeypatch):
    from margadrishti.core.config import get_settings
    from margadrishti.db.serving import _apply_runtime_secrets

    monkeypatch.setenv("MARGA_API_PASSWORD", "")
    get_settings.cache_clear()

    with pytest.raises(SystemExit, match="MARGA_API_PASSWORD"):
        _apply_runtime_secrets(object(), get_settings())
