from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Job info
    job_source = Column(String(50), default="preset")  # "preset" or "real"
    company = Column(String(255), nullable=False)
    role = Column(String(255), nullable=False)
    difficulty = Column(String(20), nullable=False)  # easy, medium, hard
    location = Column(String(255), nullable=True)

    # For real jobs from SimplifyJobs
    real_job_apply_url = Column(String(500), nullable=True)
    real_job_category = Column(String(255), nullable=True)

    # Interview stages results
    screening_passed = Column(Boolean, nullable=True)
    screening_feedback = Column(Text, nullable=True)

    technical_passed = Column(Boolean, nullable=True)
    technical_score = Column(Float, nullable=True)
    technical_details = Column(JSON, nullable=True)  # questions, answers, scores

    behavioral_passed = Column(Boolean, nullable=True)
    behavioral_score = Column(Float, nullable=True)
    behavioral_feedback = Column(Text, nullable=True)

    # Final result
    final_hired = Column(Boolean, nullable=True)
    final_weighted_score = Column(Float, nullable=True)

    # Status tracking
    completed = Column(Boolean, default=False)
    current_stage = Column(String(50), default="screening")

    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationship
    user = relationship("User", back_populates="job_applications")
