# Owner D — D-010 origin block test.
#
# Proves the server-side origin check is the real guard, not CORS.
# CORS is browser-enforced; a script with a copied widget_id ignores it.
# This test simulates that: a direct httpx POST from a non-allowlisted origin
# must be rejected with HTTP 403, regardless of any browser header behaviour.
#
# Strategy: FastAPI TestClient (uses httpx internally) with get_session overridden
# to yield a mock session that returns a known-shape Widget. The signing key is
# set directly on app.state since lifespan (which loads it from Vault) is skipped
# in tests. No live Postgres / Vault / Redis is required.

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_session
from app.main import app
from app.models.widget import Widget


def _build_widget(allowed_origins: list[str], is_active: bool = True) -> Widget:
    """Construct an in-memory Widget without touching the DB."""
    widget = Widget()
    widget.id = uuid.uuid4()
    widget.tenant_id = uuid.uuid4()
    widget.name = "Test Widget"
    widget.allowed_origins = allowed_origins
    widget.greeting = "Hi!"
    widget.persona_name = "Bot"
    widget.is_active = is_active
    return widget


@pytest.fixture
def allowed_widget() -> Widget:
    return _build_widget(allowed_origins=["https://allowed.example.com"])


@pytest.fixture
def inactive_widget() -> Widget:
    return _build_widget(allowed_origins=["https://allowed.example.com"], is_active=False)


@pytest.fixture
def client_for():
    """
    Yields a factory that builds a TestClient bound to a specific widget.
    The factory installs the dependency override; teardown clears it.
    """

    def _make(widget):
        async def fake_get_session():
            session = AsyncMock()
            session.get = AsyncMock(return_value=widget)
            yield session

        app.dependency_overrides[get_session] = fake_get_session
        # Lifespan does not run in TestClient unless used as a context manager,
        # so the signing key is set directly here.
        app.state.widget_signing_key = "test-signing-key-do-not-use-in-prod"
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


# ── D-010 — the contract test ─────────────────────────────────────────────────

def test_disallowed_origin_returns_403(client_for, allowed_widget):
    """A non-browser HTTP client posting from a disallowed origin gets 403."""
    client = client_for(allowed_widget)

    response = client.post(
        "/api/v1/widget/token",
        json={
            "widget_id": str(allowed_widget.id),
            "origin": "https://attacker.example.com",
        },
    )

    assert response.status_code == 403
    assert response.headers.get("X-Error-Code") == "ORIGIN_BLOCKED"


# ── Sanity tests for the happy path and adjacent error paths ──────────────────

def test_allowed_origin_returns_token(client_for, allowed_widget):
    """An allowlisted origin receives a signed token, session_id, and expires_at."""
    client = client_for(allowed_widget)

    response = client.post(
        "/api/v1/widget/token",
        json={
            "widget_id": str(allowed_widget.id),
            "origin": "https://allowed.example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["token"], str) and len(body["token"]) > 0
    assert uuid.UUID(body["session_id"])
    assert "expires_at" in body


def test_unknown_widget_returns_404(client_for):
    """A widget_id that doesn't exist returns 404 (no widget enumeration leak)."""
    client = client_for(None)

    response = client.post(
        "/api/v1/widget/token",
        json={
            "widget_id": str(uuid.uuid4()),
            "origin": "https://allowed.example.com",
        },
    )

    assert response.status_code == 404


def test_inactive_widget_returns_404(client_for, inactive_widget):
    """An is_active=false widget is indistinguishable from not-found."""
    client = client_for(inactive_widget)

    response = client.post(
        "/api/v1/widget/token",
        json={
            "widget_id": str(inactive_widget.id),
            "origin": "https://allowed.example.com",
        },
    )

    assert response.status_code == 404


def test_config_endpoint_returns_widget_config(client_for, allowed_widget):
    """GET /{id}/config returns greeting + persona_name + theme."""
    client = client_for(allowed_widget)

    response = client.get(f"/api/v1/widget/{allowed_widget.id}/config")

    assert response.status_code == 200
    body = response.json()
    assert body["greeting"] == allowed_widget.greeting
    assert body["persona_name"] == allowed_widget.persona_name
    assert "primary_color" in body["theme"]


def test_config_endpoint_inactive_widget_returns_404(client_for, inactive_widget):
    client = client_for(inactive_widget)

    response = client.get(f"/api/v1/widget/{inactive_widget.id}/config")

    assert response.status_code == 404
