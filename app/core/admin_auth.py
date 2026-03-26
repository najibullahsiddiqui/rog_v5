from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

from app.core.config import ADMIN_SESSION_COOKIE, ADMIN_TOKEN


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_valid_admin_token(token: str | None) -> bool:
    provided = (token or "").strip()
    expected = (ADMIN_TOKEN or "").strip()
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided, expected)


def session_cookie_value() -> str:
    token = (ADMIN_TOKEN or "").strip()
    if not token:
        return ""
    return _token_hash(token)


def is_admin_authorized(request: Request) -> bool:
    expected_cookie = session_cookie_value()
    cookie_value = (request.cookies.get(ADMIN_SESSION_COOKIE) or "").strip()
    if expected_cookie and cookie_value and hmac.compare_digest(cookie_value, expected_cookie):
        return True

    header_token = (request.headers.get("x-admin-token") or "").strip()
    return is_valid_admin_token(header_token)
