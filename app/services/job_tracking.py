"""Job tracking service for persisting simulation results."""

from datetime import datetime
from sqlalchemy.orm import Session
from app.models.job_application import JobApplication
from app.models.user import User, UserProfile


def create_job_application(
    db: Session,
    user: User,
    company: str,
    role: str,
    difficulty: str,
    job_source: str = "preset",
    location: str = None,
    apply_url: str = None,
    category: str = None,
) -> JobApplication:
    """Create a new job application record."""
    job_app = JobApplication(
        user_id=user.id,
        company=company or "Unknown",
        role=role,
        difficulty=difficulty,
        job_source=job_source,
        location=location,
        real_job_apply_url=apply_url,
        real_job_category=category,
        current_stage="screening",
    )
    db.add(job_app)
    db.commit()
    db.refresh(job_app)

    # Update user's total simulations count
    if user.profile:
        user.profile.total_simulations += 1
        db.commit()

    return job_app


def update_screening_result(
    db: Session,
    job_app: JobApplication,
    passed: bool,
    feedback: str,
) -> JobApplication:
    """Update job application with screening results."""
    job_app.screening_passed = passed
    job_app.screening_feedback = feedback
    job_app.current_stage = "technical" if passed else "result"

    if not passed:
        job_app.completed = True
        job_app.completed_at = datetime.utcnow()
        job_app.final_hired = False

    db.commit()
    db.refresh(job_app)
    return job_app


def update_technical_result(
    db: Session,
    job_app: JobApplication,
    passed: bool,
    score: float,
    details: dict = None,
) -> JobApplication:
    """Update job application with technical interview results."""
    job_app.technical_passed = passed
    job_app.technical_score = score
    job_app.technical_details = details
    job_app.current_stage = "behavioral" if passed else "result"

    if not passed:
        job_app.completed = True
        job_app.completed_at = datetime.utcnow()
        job_app.final_hired = False

    db.commit()
    db.refresh(job_app)
    return job_app


def update_behavioral_result(
    db: Session,
    job_app: JobApplication,
    passed: bool,
    score: float,
    feedback: str = None,
) -> JobApplication:
    """Update job application with behavioral interview results."""
    job_app.behavioral_passed = passed
    job_app.behavioral_score = score
    job_app.behavioral_feedback = feedback
    job_app.current_stage = "result"

    db.commit()
    db.refresh(job_app)
    return job_app


def finalize_job_application(
    db: Session,
    job_app: JobApplication,
    hired: bool,
    weighted_score: float,
) -> JobApplication:
    """Finalize the job application with final result."""
    job_app.final_hired = hired
    job_app.final_weighted_score = weighted_score
    job_app.completed = True
    job_app.completed_at = datetime.utcnow()

    db.commit()
    db.refresh(job_app)

    # Update user's successful simulations if hired
    if hired:
        user = db.query(User).filter(User.id == job_app.user_id).first()
        if user and user.profile:
            user.profile.successful_simulations += 1
            db.commit()

    return job_app


def get_job_application(db: Session, job_id: int, user_id: int) -> JobApplication:
    """Get a job application by ID for a specific user."""
    return db.query(JobApplication).filter(
        JobApplication.id == job_id,
        JobApplication.user_id == user_id,
    ).first()
