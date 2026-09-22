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
from typing import Optional
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


def is_auth_required() -> bool:
    """
    Check if authentication is strictly enforced.
    Returns True if AUTH_ENABLED is explicitly 'true' or if Supabase is configured and not explicitly disabled.
    """
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
    if jwt_secret:
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
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
        except jwt.InvalidTokenError as ex:
            logger.warning(f"JWT signature verification failed: {type(ex).__name__}")
            # Fall through to Supabase client check

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


def get_user_profile_from_db(user_id: str, default_email: str = "") -> UserProfile:
    """Fetch user role and full name from public.profiles table."""
    client = get_supabase_client()
    if client:
        try:
            res = client.table("profiles").select("id, email, full_name, role").eq("id", user_id).limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                return UserProfile(
                    id=row.get("id", user_id),
                    email=row.get("email", default_email),
                    full_name=row.get("full_name"),
                    role=row.get("role", "user")
                )
        except Exception as ex:
            logger.warning(f"Could not load user profile from DB: {type(ex).__name__}")

    return UserProfile(
        id=user_id,
        email=default_email,
        full_name=None,
        role="user"
    )


async def get_current_user(
    token: Optional[str] = Depends(extract_token)
) -> UserProfile:
    """
    FastAPI dependency that enforces authentication.
    Returns the authenticated UserProfile.
    """
    if not is_auth_required():
        # In non-auth development mode, allow default system user
        if not token:
            return UserProfile(
                id=os.getenv("DEFAULT_DEV_USER_ID", DEFAULT_MOCK_USER_ID),
                email="dev@company.local",
                full_name="Development User",
                role="admin"  # Allow admin operations in dev mode without auth
            )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = verify_supabase_jwt(token)
    user_id = claims.get("sub")
    if not user_id:
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

    return profile


async def get_optional_user(
    token: Optional[str] = Depends(extract_token)
) -> Optional[UserProfile]:
    """Returns the current user if a valid token is provided, or None."""
    if not token:
        return None
    try:
        return await get_current_user(token)
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
