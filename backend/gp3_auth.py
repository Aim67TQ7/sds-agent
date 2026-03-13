"""
GP3 Unified Auth Middleware
Drop this file into any FastAPI service to enable SSO via .gp3.app cookies.

Usage:
    from gp3_auth import get_gp3_user, require_app, set_auth_cookies, clear_auth_cookies

    @app.get("/protected")
    def protected(user = Depends(get_gp3_user)):
        return {"email": user["email"], "company": user["company_name"]}

    @app.get("/cal-only")
    def cal_only(user = Depends(require_app("cal"))):
        return {"company_id": user["company_id"]}
"""
import os
import math
import logging
from typing import Optional
from functools import lru_cache
from fastapi import Request, HTTPException, Depends
from fastapi.responses import Response
from supabase import create_client, Client
import httpx

logger = logging.getLogger("gp3_auth")

# ── Config ───────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ezlmmegowggujpcnzoda.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_KEY", ""))
COOKIE_DOMAIN = os.getenv("GP3_COOKIE_DOMAIN", ".gp3.app")
COOKIE_PREFIX = "gp3_auth"
COOKIE_CHUNK_SIZE = 3800  # Keep under 4KB per cookie
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_supabase: Optional[Client] = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase


# ── Cookie Chunking ──────────────────────────────────────────

def set_auth_cookies(response: Response, access_token: str, refresh_token: str = ""):
    """Set chunked auth cookies on .gp3.app domain."""
    # Chunk access token
    chunks = _chunk_string(access_token, COOKIE_CHUNK_SIZE)
    for i, chunk in enumerate(chunks):
        response.set_cookie(
            key=f"{COOKIE_PREFIX}_{i}",
            value=chunk,
            domain=COOKIE_DOMAIN,
            path="/",
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
        )
    # Store chunk count
    response.set_cookie(
        key=f"{COOKIE_PREFIX}_count",
        value=str(len(chunks)),
        domain=COOKIE_DOMAIN,
        path="/",
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )
    # Refresh token (single cookie)
    if refresh_token:
        response.set_cookie(
            key=f"{COOKIE_PREFIX}_refresh",
            value=refresh_token,
            domain=COOKIE_DOMAIN,
            path="/",
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=COOKIE_MAX_AGE,
        )


def clear_auth_cookies(response: Response):
    """Clear all auth cookies."""
    for i in range(10):  # Clear up to 10 chunks
        response.delete_cookie(key=f"{COOKIE_PREFIX}_{i}", domain=COOKIE_DOMAIN, path="/")
    response.delete_cookie(key=f"{COOKIE_PREFIX}_count", domain=COOKIE_DOMAIN, path="/")
    response.delete_cookie(key=f"{COOKIE_PREFIX}_refresh", domain=COOKIE_DOMAIN, path="/")


def _get_token_from_cookies(request: Request) -> Optional[str]:
    """Reassemble JWT from chunked cookies."""
    count_str = request.cookies.get(f"{COOKIE_PREFIX}_count")
    if not count_str:
        return None
    try:
        count = int(count_str)
    except ValueError:
        return None

    chunks = []
    for i in range(count):
        chunk = request.cookies.get(f"{COOKIE_PREFIX}_{i}")
        if chunk is None:
            return None
        chunks.append(chunk)

    return "".join(chunks)


def _get_token_from_header(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _chunk_string(s: str, size: int) -> list:
    return [s[i:i + size] for i in range(0, len(s), size)]


# ── Token Validation ─────────────────────────────────────────

def _validate_token(token: str) -> Optional[dict]:
    """Validate Supabase JWT and return user info."""
    try:
        # Use Supabase's auth.getUser() which validates the JWT server-side
        headers = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {token}",
        }
        resp = httpx.get(f"{SUPABASE_URL}/auth/v1/user", headers=headers, timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return None


def _get_profile(auth_id: str = None, email: str = None) -> Optional[dict]:
    """Fetch gp3_profiles row by auth_id or email."""
    sb = _get_supabase()
    try:
        if auth_id:
            r = sb.table("gp3_profiles").select("*").eq("auth_id", auth_id).limit(1).execute()
            if r.data:
                return r.data[0]
        if email:
            r = sb.table("gp3_profiles").select("*").eq("email", email).limit(1).execute()
            if r.data:
                return r.data[0]
    except Exception as e:
        logger.warning(f"Profile lookup failed: {e}")
    return None


# ── FastAPI Dependencies ─────────────────────────────────────

def get_gp3_user(request: Request) -> dict:
    """
    FastAPI dependency: extract and validate user from cookies or Authorization header.
    Returns profile dict with company_id, tenant_id, allowed_apps, etc.
    """
    # Try cookie first, then header
    token = _get_token_from_cookies(request) or _get_token_from_header(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated — no token found")

    # Validate with Supabase
    auth_user = _validate_token(token)
    if not auth_user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    auth_id = auth_user.get("id")
    email = auth_user.get("email")

    # Fetch profile
    profile = _get_profile(auth_id=auth_id, email=email)
    if not profile:
        raise HTTPException(status_code=403, detail=f"No GP3 profile found for {email}. Contact admin.")

    if not profile.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Auto-link auth_id if not yet linked
    if profile.get("auth_id") is None and auth_id:
        try:
            sb = _get_supabase()
            sb.table("gp3_profiles").update({
                "auth_id": auth_id,
                "last_login": "now()",
            }).eq("id", profile["id"]).execute()
            profile["auth_id"] = auth_id
        except Exception:
            pass

    # Attach raw token for downstream use
    profile["_token"] = token
    profile["_auth_id"] = auth_id

    return profile


def require_app(app_name: str):
    """
    FastAPI dependency factory: require user has access to a specific app.

    Usage:
        @app.get("/endpoint")
        def endpoint(user = Depends(require_app("cal"))):
            ...
    """
    def _check(user: dict = Depends(get_gp3_user)) -> dict:
        allowed = user.get("allowed_apps") or []
        if app_name not in allowed and user.get("role") != "admin":
            raise HTTPException(
                status_code=403,
                detail=f"You don't have access to {app_name}. Contact your admin.",
            )
        return user

    return _check
