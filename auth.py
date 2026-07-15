"""Commutr API authentication with token caching."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests
from requests.exceptions import RequestException

CACHE_DIR = os.path.expanduser("~/.commutr")
TOKEN_CACHE = os.path.join(CACHE_DIR, "token.json")


def _load_dotenv() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

API_BASE = os.getenv("COMMUTR_API_BASE", "http://localhost:8080")
COMMUTR_EMAIL = os.getenv("COMMUTR_EMAIL", "")
COMMUTR_PASSWORD = os.getenv("COMMUTR_PASSWORD", "")


class AuthError(Exception):
    pass


class TokenExpiredError(AuthError):
    pass


def _read_cached_token() -> dict | None:
    if not os.path.exists(TOKEN_CACHE):
        return None
    try:
        with open(TOKEN_CACHE) as f:
            data = json.load(f)
        if "access_token" not in data or "expires_at" not in data:
            return None
        return data
    except (json.JSONDecodeError, KeyError):
        return None


def _write_cached_token(data: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(TOKEN_CACHE, "w") as f:
        json.dump(data, f)
    os.chmod(TOKEN_CACHE, 0o600)


def _login() -> str:
    if not COMMUTR_EMAIL or not COMMUTR_PASSWORD:
        raise AuthError(
            "COMMUTR_EMAIL and COMMUTR_PASSWORD must be set in ~/.commutr/.env"
        )

    try:
        resp = requests.post(
            f"{API_BASE}/api/v1/auth/login",
            json={"email": COMMUTR_EMAIL, "password": COMMUTR_PASSWORD},
            timeout=10,
        )
    except RequestException as e:
        raise AuthError(f"Cannot reach Commutr API at {API_BASE}: {e}") from e

    if resp.status_code == 401:
        raise AuthError("Invalid credentials — check COMMUTR_EMAIL and COMMUTR_PASSWORD")
    if not resp.ok:
        body = resp.text[:300]
        raise AuthError(f"Login failed (HTTP {resp.status_code}): {body}")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise AuthError("Login response missing access_token")

    expires_in = data.get("expires_in", 86400)
    expires_at = datetime.now(timezone.utc).isoformat()

    _write_cached_token({
        "access_token": access_token,
        "refresh_token": data.get("refresh_token"),
        "expires_at": expires_at,
        "expires_in": expires_in,
    })
    return access_token


def _refresh_token(refresh_token: str) -> str:
    try:
        resp = requests.post(
            f"{API_BASE}/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=10,
        )
    except RequestException as e:
        raise AuthError(f"Token refresh failed: {e}") from e

    if not resp.ok:
        raise TokenExpiredError("Refresh token expired — re-login required")

    data = resp.json()
    access_token = data.get("access_token")
    if not access_token:
        raise AuthError("Refresh response missing access_token")

    expires_in = data.get("expires_in", 86400)
    _write_cached_token({
        "access_token": access_token,
        "refresh_token": data.get("refresh_token"),
        "expires_at": datetime.now(timezone.utc).isoformat(),
        "expires_in": expires_in,
    })
    return access_token


def get_token() -> str:
    cached = _read_cached_token()

    if cached:
        try:
            expires_at = datetime.fromisoformat(cached["expires_at"])
            expires_in = cached.get("expires_in", 86400)
            now = datetime.now(timezone.utc)
            if (now - expires_at).total_seconds() < expires_in:
                return cached["access_token"]

            refresh = cached.get("refresh_token")
            if refresh:
                try:
                    return _refresh_token(refresh)
                except TokenExpiredError:
                    pass
        except (ValueError, KeyError):
            pass

    return _login()


def clear_token() -> None:
    if os.path.exists(TOKEN_CACHE):
        os.remove(TOKEN_CACHE)


def get_api_base() -> str:
    return API_BASE
