"""Google sign-in: the frontend sends the GIS ID token as `Authorization: Bearer <token>`."""
import hmac

from fastapi import Header, HTTPException
from google.auth.transport.requests import Request
from google.oauth2 import id_token

from . import config


def current_user(authorization: str = Header("")):
    """Returns the Google account id (`sub`) of the caller, or 401."""
    token = authorization.removeprefix("Bearer ").strip()
    if config.DEV_AUTH and token:
        return token
    if not token or not config.GOOGLE_CLIENT_ID:
        raise HTTPException(401, "sign in with Google")
    try:
        return id_token.verify_oauth2_token(token, Request(), config.GOOGLE_CLIENT_ID)["sub"]
    except ValueError as e:
        raise HTTPException(401, f"bad Google token: {e}") from e


def require_admin(x_admin_token: str = Header("")):
    if not config.ADMIN_TOKEN or not hmac.compare_digest(x_admin_token, config.ADMIN_TOKEN):
        raise HTTPException(403, "admin token required")
