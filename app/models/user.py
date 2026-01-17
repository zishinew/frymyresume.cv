from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Null for OAuth-only users

    # OAuth fields
    auth_provider = Column(String(20), default="local")  # local, google, github
    oauth_id = Column(String(255), nullable=True)

    # User info
    username = Column("full_name", String(255), nullable=False)
    profile_picture = Column(String(500), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    profile = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    job_applications = relationship(
        "JobApplication", back_populates="user", cascade="all, delete-orphan"
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    # Resume info
    current_resume_text = Column(Text, nullable=True)
    resume_score = Column(Integer, nullable=True)
    resume_analysis = Column(Text, nullable=True)  # JSON stored as text

    # User preferences
    target_role = Column(String(255), nullable=True)
    preferred_difficulty = Column(String(20), default="medium")

    # Stats
    total_simulations = Column(Integer, default=0)
    successful_simulations = Column(Integer, default=0)  # Jobs "gotten into"

    # Timestamps
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    user = relationship("User", back_populates="profile")
