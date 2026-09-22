"""
auth_dependencies.py
FastAPI Authentication & Authorization Dependencies using Supabase:
- Verifies Supabase Bearer JWT tokens cryptographically
- Extracts canonical user_id (auth.users UUID), email, and role
- Queries public.profiles to enforce role-based access control (user vs admin)
- Protects endpoints from unauthorized access and cross-user data leakage
- Zero leak of secrets, keys, or stack traces
"""

import os
from typing import Any, Optional
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Header, Query, Request, status
import jwt
import logging_utils
from supabase_client import get_supabase_client, get_supabase_jwt_secret, is_supabase_configured

logger = logging_utils.get_logger("company_server_ocr.auth")

DEFAULT_MOCK_USER_ID = "00000000-0000-0000-0000-000000000001"


class UserProfile(BaseModel):
    id: str = Field(..., description="Canonical UUID from Supabase auth.users")
    email: str = Field(..., description="User email address")
    full_name: Optional[str] = Field(None, description="User full name")
    role: str = Field("user", description="Role: 'user' or 'admin'")

    def get(self, key: str, default: Any = None) -> Any:
        if key in ("sub", "user_id", "id"):
            return self.id
        return getattr(self, key, default)

    def __getitem__(self, item: str) -> Any:
        val = self.get(item)
        if val is None and item not in ("full_name",):
            raise KeyError(item)
        return val


def is_auth_required() -> bool:
    """
    Check if authentication is strictly enforced.
    Returns True if AUTH_ENABLED is explicitly 'true' or if Supabase is configured and not explicitly disabled.
    """
    auth_mode = os.getenv("AUTH_MODE", "").lower().strip()
    if auth_mode == "disabled":
        return False
    env_val = os.getenv("AUTH_ENABLED", "").lower().strip()
    if env_val in ("false", "0", "no"):
        return False
    if env_val in ("true", "1", "yes"):
        return True
    # If Supabase is configured, default to requiring auth
    return is_supabase_configured()


def extract_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    token_query: Optional[str] = Query(None, alias="token")
) -> Optional[str]:
    """Extract Bearer token from Authorization header or URL token parameter."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if token_query:
        return token_query.strip()
    return None


def verify_supabase_jwt(token: str) -> dict:
    """
    Verify and decode Supabase JWT token.
    1. First tries local cryptographic verification using SUPABASE_JWT_SECRET (HS256).
    2. Fallbacks to Supabase Auth API if client is available.
    Raises HTTPException(401) on failure.
    """
    # 1. Local JWT Secret Verification
    jwt_secret = get_supabase_jwt_secret()
    legacy_secret = os.getenv("JWT_SECRET") or "company-ocr-default-jwt-secret-key-change-in-prod-32chars"
    secrets_to_try = [s for s in (jwt_secret, legacy_secret) if s]

    for secret in secrets_to_try:
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_exp": True}
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please sign in again.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            pass

    # 2. Supabase Auth API Verification
    client = get_supabase_client()
    if client:
        try:
            auth_resp = client.auth.get_user(token)
            if auth_resp and auth_resp.user:
                return {
                    "sub": auth_resp.user.id,
                    "email": auth_resp.user.email,
                    "user_metadata": auth_resp.user.user_metadata or {},
                    "app_metadata": auth_resp.user.app_metadata or {},
                }
        except Exception as ex:
            logger.warning(f"Supabase client token validation failed: {type(ex).__name__}")

    # If all verification attempts failed
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def is_admin_email(email: str) -> bool:
    """Check if email matches configured ADMIN_EMAILS whitelist."""
    if not email:
        return False
    admin_list = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
    return email.strip().lower() in admin_list


def get_user_profile_from_db(user_id: str, default_email: str = "") -> UserProfile:
    """Fetch user role and full name from public.profiles table."""
    client = get_supabase_client()
    if client:
        try:
            res = client.table("profiles").select("id, email, full_name, role").eq("id", user_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                role = row.get("role", "user")
                user_email = row.get("email", default_email)
                if role != "admin" and is_admin_email(user_email):
                    role = "admin"
                    try:
                        client.table("profiles").update({"role": "admin"}).eq("id", user_id).execute()
                    except Exception:
                        pass
                return UserProfile(
                    id=row.get("id", user_id),
                    email=user_email,
                    full_name=row.get("full_name"),
                    role=role,
                )
        except Exception as ex:
            logger.warning(f"Could not load user profile from DB: {type(ex).__name__}")

    role = "admin" if is_admin_email(default_email) else "user"
    return UserProfile(
        id=user_id,
        email=default_email,
        full_name=None,
        role=role,
    )


async def get_current_user(
    request: Request = None,
    token: Optional[str] = Depends(extract_token)
) -> UserProfile:
    """
    FastAPI dependency that enforces authentication.
    Returns the authenticated UserProfile.
    Logs structured auth outcome without exposing tokens or secrets.
    """
    req_path = request.url.path if request and hasattr(request, "url") else "unknown"

    if not is_auth_required():
        # In non-auth development mode, allow default system user
        if not token:
            user = UserProfile(
                id=os.getenv("DEFAULT_DEV_USER_ID", DEFAULT_MOCK_USER_ID),
                email="dev@company.local",
                full_name="Development User",
                role="admin"  # Allow admin operations in dev mode without auth
            )
            if request and hasattr(request, "state"):
                request.state.user_id = user.id
            logger.info(f"[AUTH_LOG] path={req_path} user_id={user.id} auth_result=dev_bypass status_code=200")
            return user

    if not token:
        logger.warning(f"[AUTH_LOG] path={req_path} user_id=None auth_result=failed reason=missing_token status_code=401")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided (Bearer JWT required).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = verify_supabase_jwt(token)
    user_id = claims.get("sub")
    if not user_id:
        logger.warning(f"[AUTH_LOG] path={req_path} user_id=None auth_result=failed reason=missing_sub status_code=401")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims: missing subject identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = claims.get("email", "")
    profile = get_user_profile_from_db(user_id, default_email=email)

    # If role was set in claims or metadata, use it if profile didn't specify admin
    if profile.role != "admin":
        role_claim = (
            claims.get("app_metadata", {}).get("role") or
            claims.get("user_metadata", {}).get("role")
        )
        if role_claim == "admin":
            profile.role = "admin"

    if request and hasattr(request, "state"):
        request.state.user_id = profile.id
    logger.info(f"[AUTH_LOG] path={req_path} user_id={profile.id} auth_result=success status_code=200")
    return profile


async def get_optional_user(
    request: Request = None,
    token: Optional[str] = Depends(extract_token)
) -> Optional[UserProfile]:
    """Returns the current user if a valid token is provided, or None."""
    if not token:
        return None
    try:
        return await get_current_user(request=request, token=token)
    except HTTPException:
        return None


async def require_admin(
    current_user: UserProfile = Depends(get_current_user)
) -> UserProfile:
    """
    Enforces that the authenticated user possesses the 'admin' role.
    Raises HTTP 403 Forbidden for non-admin users.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this administrative action."
        )
    return current_user
