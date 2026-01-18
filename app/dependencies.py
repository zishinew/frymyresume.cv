from typing import Optional
import json
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
from app.config import SUPABASE_JWT_SECRET
from app.supabase_client import get_supabase_admin
import os

security = HTTPBearer(auto_error=False)

# Get the public key for ES256 verification (if available)
# Can be either PEM format or JWK JSON format
_raw_public_key = os.getenv("SUPABASE_JWT_PUBLIC_KEY", "")

# Parse public key - handle both PEM and JWK formats
SUPABASE_JWT_PUBLIC_KEY = None
if _raw_public_key:
    if _raw_public_key.startswith("-----BEGIN"):
        # PEM format
        SUPABASE_JWT_PUBLIC_KEY = _raw_public_key.replace("\\n", "\n")
    elif _raw_public_key.startswith("{"):
        # JWK JSON format - parse and use directly
        try:
            SUPABASE_JWT_PUBLIC_KEY = json.loads(_raw_public_key)
        except json.JSONDecodeError:
            print("Warning: Could not parse SUPABASE_JWT_PUBLIC_KEY as JWK")


class SupabaseUser(BaseModel):
    """Represents an authenticated Supabase user."""
    id: str  # UUID as string
    email: str
    username: str
    profile_picture: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    auth_provider: str = "email"
    is_verified: bool = False


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> SupabaseUser:
    """Get the current authenticated user from Supabase JWT."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Decode and verify Supabase JWT
        # Support both ES256 (new) and HS256 (legacy) algorithms
        if SUPABASE_JWT_PUBLIC_KEY:
            # New ES256 signing with public key
            payload = jwt.decode(
                token,
                SUPABASE_JWT_PUBLIC_KEY,
                algorithms=["ES256"],
                audience="authenticated",
            )
        else:
            # Legacy HS256 signing with shared secret
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        # Fetch user profile from Supabase
        supabase = get_supabase_admin()
        profile_response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()

        profile = profile_response.data if profile_response.data else {}

        # Determine auth provider from app_metadata
        app_metadata = payload.get("app_metadata", {})
        provider = app_metadata.get("provider", "email")

        return SupabaseUser(
            id=user_id,
            email=payload.get("email", ""),
            username=profile.get("username", payload.get("email", "").split("@")[0]),
            profile_picture=profile.get("profile_picture"),
            is_active=profile.get("is_active", True),
            created_at=profile.get("created_at"),
            auth_provider=provider,
            is_verified=payload.get("email_confirmed_at") is not None,
        )

    except JWTError as e:
        print(f"JWT Error: {e}")
        print(f"Token (first 50 chars): {token[:50]}...")
        print(f"Secret (first 20 chars): {SUPABASE_JWT_SECRET[:20] if SUPABASE_JWT_SECRET else 'None'}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Optional[SupabaseUser]:
    """Get the current user if authenticated, None otherwise."""
    if not credentials:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
