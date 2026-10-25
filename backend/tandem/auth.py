"""Simple user ids: the client makes up a random id, keeps it, and sends it as `Authorization: Bearer <id>`."""
import hashlib
import hmac
import re

from fastapi import Header, HTTPException

from . import config

# shortcut: anyone who learns an id can act as that user; add real sign-in if accounts ever need protecting.
USER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def current_user(authorization: str = Header("")):
    """Returns the caller's user id, or 401."""
    token = authorization.removeprefix("Bearer ").strip()
    if re.fullmatch(r"guest-[a-f0-9]{64}", token):
        return "guest:" + hashlib.sha256(token.encode()).hexdigest()
    if not USER_ID.fullmatch(token):
        raise HTTPException(401, "missing or malformed user id")
    return token


def require_admin(x_admin_token: str = Header("")):
    if not config.ADMIN_TOKEN or not hmac.compare_digest(x_admin_token, config.ADMIN_TOKEN):
        raise HTTPException(403, "admin token required")
