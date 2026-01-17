from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserProfile
from app.schemas.user import UserCreate, TokenResponse, RefreshTokenRequest, UserResponse
from app.services.auth import (
    get_password_hash,
    verify_password,
    create_tokens,
    decode_token,
)
from app.services.oauth import oauth
from app.dependencies import get_current_user
from app.config import FRONTEND_URL, BACKEND_URL

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user with email and password."""
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        username=user_data.username,
        auth_provider="local",
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create profile
    profile = UserProfile(user_id=user.id)
    db.add(profile)
    db.commit()

    return create_tokens(user.id)


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Login with email and password."""
    user = db.query(User).filter(User.email == form_data.username).first()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
        )

    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()

    return create_tokens(user.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """Refresh access token using refresh token."""
    payload = decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return create_tokens(user.id)


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user


# Google OAuth
@router.get("/google")
async def google_login(request: Request):
    """Initiate Google OAuth login."""
    if not hasattr(oauth, "google"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )
    redirect_uri = f"{BACKEND_URL}/api/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback."""
    if not hasattr(oauth, "google"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured",
        )

    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo")

    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to get user info from Google",
        )

    email = user_info.get("email")
    oauth_id = user_info.get("sub")

    # Check if user exists
    user = db.query(User).filter(User.email == email).first()

    if user:
        # Update OAuth info if needed
        if user.auth_provider == "local":
            user.auth_provider = "google"
            user.oauth_id = oauth_id
        user.last_login = datetime.utcnow()
        if user_info.get("picture"):
            user.profile_picture = user_info.get("picture")
        db.commit()
    else:
        # Create new user
        user = User(
            email=email,
            username=user_info.get("name") or email.split("@", 1)[0],
            profile_picture=user_info.get("picture"),
            auth_provider="google",
            oauth_id=oauth_id,
            is_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create profile
        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.commit()

    tokens = create_tokens(user.id)

    # Redirect to frontend with tokens
    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"?access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
    )
    return RedirectResponse(url=redirect_url)


# GitHub OAuth
@router.get("/github")
async def github_login(request: Request):
    """Initiate GitHub OAuth login."""
    if not hasattr(oauth, "github"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured",
        )
    redirect_uri = f"{BACKEND_URL}/api/auth/github/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/github/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    """Handle GitHub OAuth callback."""
    if not hasattr(oauth, "github"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured",
        )

    token = await oauth.github.authorize_access_token(request)

    # Get user info from GitHub API
    resp = await oauth.github.get("user", token=token)
    user_info = resp.json()

    # Get email (may need separate request if not public)
    email = user_info.get("email")
    if not email:
        email_resp = await oauth.github.get("user/emails", token=token)
        emails = email_resp.json()
        primary_email = next((e for e in emails if e.get("primary")), None)
        if primary_email:
            email = primary_email.get("email")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not get email from GitHub",
        )

    oauth_id = str(user_info.get("id"))

    # Check if user exists
    user = db.query(User).filter(User.email == email).first()

    if user:
        if user.auth_provider == "local":
            user.auth_provider = "github"
            user.oauth_id = oauth_id
        user.last_login = datetime.utcnow()
        if user_info.get("avatar_url"):
            user.profile_picture = user_info.get("avatar_url")
        db.commit()
    else:
        user = User(
            email=email,
            username=user_info.get("login") or user_info.get("name") or email.split("@", 1)[0],
            profile_picture=user_info.get("avatar_url"),
            auth_provider="github",
            oauth_id=oauth_id,
            is_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        profile = UserProfile(user_id=user.id)
        db.add(profile)
        db.commit()

    tokens = create_tokens(user.id)

    redirect_url = (
        f"{FRONTEND_URL}/auth/callback"
        f"?access_token={tokens['access_token']}"
        f"&refresh_token={tokens['refresh_token']}"
    )
    return RedirectResponse(url=redirect_url)
