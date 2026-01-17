from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User, UserProfile
from app.schemas.user import UserResponse, UserProfileResponse, AccountUpdateRequest, PasswordUpdateRequest
from app.dependencies import get_current_user
from app.services.auth import verify_password, get_password_hash
from app.config import BACKEND_URL
from pydantic import BaseModel
from typing import Optional
import os
import uuid

router = APIRouter(prefix="/api/users", tags=["users"])

UPLOADS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
os.makedirs(UPLOADS_DIR, exist_ok=True)


class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    target_role: Optional[str] = None
    preferred_difficulty: Optional[str] = None


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get current user's profile."""
    if not current_user.profile:
        # Create profile if it doesn't exist
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    return current_user.profile


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    update_data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update current user's profile."""
    profile = current_user.profile
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    # Update user fields
    if update_data.username is not None:
        current_user.username = update_data.username

    # Update profile fields
    if update_data.target_role is not None:
        profile.target_role = update_data.target_role
    if update_data.preferred_difficulty is not None:
        if update_data.preferred_difficulty in ["easy", "medium", "hard"]:
            profile.preferred_difficulty = update_data.preferred_difficulty

    db.commit()
    db.refresh(profile)
    return profile


@router.get("/me/full")
async def get_full_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full user info including profile and stats."""
    profile = current_user.profile
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "profile_picture": current_user.profile_picture,
            "auth_provider": current_user.auth_provider,
            "is_verified": current_user.is_verified,
            "created_at": current_user.created_at,
        },
        "profile": {
            "id": profile.id,
            "resume_score": profile.resume_score,
            "target_role": profile.target_role,
            "preferred_difficulty": profile.preferred_difficulty,
            "total_simulations": profile.total_simulations,
            "successful_simulations": profile.successful_simulations,
            "updated_at": profile.updated_at,
        },
    }


@router.put("/account", response_model=UserResponse)
async def update_account(
    update_data: AccountUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update account settings (username, email, profile picture)."""
    if update_data.email and update_data.email != current_user.email:
        existing_user = db.query(User).filter(User.email == update_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use",
            )
        current_user.email = update_data.email

    if update_data.username is not None:
        if not update_data.username.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username cannot be empty",
            )
        current_user.username = update_data.username.strip()

    if update_data.profile_picture is not None:
        profile_picture = update_data.profile_picture.strip()
        current_user.profile_picture = profile_picture or None

    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/password")
async def update_password(
    update_data: PasswordUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update account password."""
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password not set for this account",
        )

    if not verify_password(update_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(update_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    current_user.hashed_password = get_password_hash(update_data.new_password)
    db.commit()
    return {"status": "ok"}


@router.post("/profile-picture", response_model=UserResponse)
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and update the user's profile picture."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only image uploads are allowed",
        )

    extension = os.path.splitext(file.filename or "")[1].lower() or ".png"
    filename = f"user_{current_user.id}_{uuid.uuid4().hex}{extension}"
    file_path = os.path.join(UPLOADS_DIR, filename)

    contents = await file.read()
    with open(file_path, "wb") as output_file:
        output_file.write(contents)

    current_user.profile_picture = f"{BACKEND_URL}/uploads/{filename}"
    db.commit()
    db.refresh(current_user)
    return current_user
