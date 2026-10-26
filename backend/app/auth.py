"""Authentication and authorization.

* Dashboard users log in with email + password and get a JWT (12 h).
* The CV service authenticates with a shared API key (X-API-Key header), not a user token.
* Passwords are hashed with scrypt (stdlib), so there is no extra crypto dependency.
"""
import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import get_conn

log = logging.getLogger("gatesense.auth")

_DEFAULT_SECRET = "dev-secret-change-me"
_DEFAULT_CV_KEY = "dev-cv-key"
SECRET_KEY = os.getenv("SECRET_KEY", _DEFAULT_SECRET)
CV_API_KEY = os.getenv("CV_API_KEY", _DEFAULT_CV_KEY)
TOKEN_HOURS = 12

if SECRET_KEY == _DEFAULT_SECRET or CV_API_KEY == _DEFAULT_CV_KEY:
    log.warning("Using default SECRET_KEY / CV_API_KEY. Fine for a laptop demo, never for a real deployment.")

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except ValueError:
        return False


DUMMY_HASH = hash_password("not-a-real-password")   # burns the same time when the email is unknown


def create_token(user_id) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer), conn=Depends(get_conn)):
    if creds is None:
        raise HTTPException(401, "not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload["sub"]
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, "invalid or expired token")
    user = conn.execute(
        """SELECT u.id, u.site_id, u.email, u.role, u.unit, u.full_name, s.name AS site_name, s.timezone
           FROM users u JOIN sites s ON s.id = u.site_id WHERE u.id = %s""", (user_id,)
    ).fetchone()
    if user is None:     # deleted user: token is useless even if not expired
        raise HTTPException(401, "invalid or expired token")
    return user


def require_cv_key(x_api_key: str = Header(default="")):
    if not hmac.compare_digest(x_api_key.encode(), CV_API_KEY.encode()):
        raise HTTPException(401, "invalid API key")


def check_site(user, site_id, *roles):
    """User must belong to this site and (if roles given) have one of the roles."""
    if user["site_id"] != site_id or (roles and user["role"] not in roles):
        raise HTTPException(403, "not allowed")
    return user
