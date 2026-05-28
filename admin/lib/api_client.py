# Owner D — D-018: thin HTTP wrapper around the Concierge backend.
#
# Every page imports this; no page calls httpx directly. The bearer token comes
# from st.session_state["token"], which app.py sets after a successful login.
# A 401 anywhere clears the session and short-circuits the page so the user
# is forced back to the login screen — covers token expiry mid-session.

import os
from typing import Any

import httpx
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
WIDGET_PUBLIC_URL = os.environ.get("WIDGET_PUBLIC_URL", "http://localhost:3000")

_TIMEOUT = 15.0


def _auth_headers() -> dict[str, str]:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _handle_401(response: httpx.Response) -> None:
    if response.status_code == 401:
        st.session_state.pop("token", None)
        st.session_state.pop("role", None)
        st.error("Session expired — please sign in again.")
        st.stop()


def login(email: str, password: str) -> tuple[str | None, str | None]:
    """fastapi-users OAuth2 password flow. Returns (token, error)."""
    try:
        with httpx.Client(base_url=BACKEND_URL, timeout=_TIMEOUT) as client:
            response = client.post(
                "/api/v1/auth/login",
                data={"username": email, "password": password},
            )
    except httpx.RequestError as e:
        return None, f"Backend unreachable: {e}"

    if response.status_code != 200:
        return None, f"Login failed ({response.status_code})"

    data = response.json()
    token = data.get("access_token")
    if not token:
        return None, "Login response missing access_token"
    return token, None


def get(path: str, **params: Any) -> httpx.Response:
    with httpx.Client(base_url=BACKEND_URL, timeout=_TIMEOUT, headers=_auth_headers()) as client:
        response = client.get(path, params=params)
    _handle_401(response)
    return response


def post(path: str, json: dict[str, Any] | None = None) -> httpx.Response:
    with httpx.Client(base_url=BACKEND_URL, timeout=_TIMEOUT, headers=_auth_headers()) as client:
        response = client.post(path, json=json)
    _handle_401(response)
    return response


def put(path: str, json: dict[str, Any]) -> httpx.Response:
    with httpx.Client(base_url=BACKEND_URL, timeout=_TIMEOUT, headers=_auth_headers()) as client:
        response = client.put(path, json=json)
    _handle_401(response)
    return response


def patch(path: str) -> httpx.Response:
    with httpx.Client(base_url=BACKEND_URL, timeout=_TIMEOUT, headers=_auth_headers()) as client:
        response = client.patch(path)
    _handle_401(response)
    return response


def delete(path: str) -> httpx.Response:
    with httpx.Client(base_url=BACKEND_URL, timeout=_TIMEOUT, headers=_auth_headers()) as client:
        response = client.delete(path)
    _handle_401(response)
    return response
