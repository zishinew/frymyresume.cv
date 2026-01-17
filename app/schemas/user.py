from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    username: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    profile_picture: Optional[str]
    auth_provider: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    id: int
    resume_score: Optional[int]
    target_role: Optional[str]
    preferred_difficulty: str
    total_simulations: int
    successful_simulations: int
    updated_at: datetime

    class Config:
        from_attributes = True


class UserWithProfileResponse(BaseModel):
    user: UserResponse
    profile: Optional[UserProfileResponse]


class AccountUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    profile_picture: Optional[str] = None


class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str
