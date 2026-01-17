from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from app.database import get_db
from app.models.user import User
from app.models.job_application import JobApplication
from app.schemas.job import JobApplicationResponse, JobStatsResponse
from app.dependencies import get_current_user
from app.services.job_tracking import (
    create_job_application,
    update_screening_result,
    update_technical_result,
    update_behavioral_result,
    finalize_job_application,
    get_job_application,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# Request models for job tracking
class CreateJobRequest(BaseModel):
    company: str
    role: str
    difficulty: str
    job_source: str = "preset"
    location: Optional[str] = None
    apply_url: Optional[str] = None
    category: Optional[str] = None


class UpdateScreeningRequest(BaseModel):
    job_id: int
    passed: bool
    feedback: str


class UpdateTechnicalRequest(BaseModel):
    job_id: int
    passed: bool
    score: float
    details: Optional[dict] = None


class UpdateBehavioralRequest(BaseModel):
    job_id: int
    passed: bool
    score: float
    feedback: Optional[str] = None


class FinalizeJobRequest(BaseModel):
    job_id: int
    hired: bool
    weighted_score: float


# Job tracking endpoints
@router.post("/track/create", response_model=JobApplicationResponse)
async def track_create_job(
    request: CreateJobRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new job application to track."""
    job_app = create_job_application(
        db=db,
        user=current_user,
        company=request.company,
        role=request.role,
        difficulty=request.difficulty,
        job_source=request.job_source,
        location=request.location,
        apply_url=request.apply_url,
        category=request.category,
    )
    return job_app


@router.post("/track/screening", response_model=JobApplicationResponse)
async def track_screening_result(
    request: UpdateScreeningRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update job application with screening results."""
    job_app = get_job_application(db, request.job_id, current_user.id)
    if not job_app:
        raise HTTPException(status_code=404, detail="Job application not found")

    job_app = update_screening_result(
        db=db,
        job_app=job_app,
        passed=request.passed,
        feedback=request.feedback,
    )
    return job_app


@router.post("/track/technical", response_model=JobApplicationResponse)
async def track_technical_result(
    request: UpdateTechnicalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update job application with technical interview results."""
    job_app = get_job_application(db, request.job_id, current_user.id)
    if not job_app:
        raise HTTPException(status_code=404, detail="Job application not found")

    job_app = update_technical_result(
        db=db,
        job_app=job_app,
        passed=request.passed,
        score=request.score,
        details=request.details,
    )
    return job_app


@router.post("/track/behavioral", response_model=JobApplicationResponse)
async def track_behavioral_result(
    request: UpdateBehavioralRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update job application with behavioral interview results."""
    job_app = get_job_application(db, request.job_id, current_user.id)
    if not job_app:
        raise HTTPException(status_code=404, detail="Job application not found")

    job_app = update_behavioral_result(
        db=db,
        job_app=job_app,
        passed=request.passed,
        score=request.score,
        feedback=request.feedback,
    )
    return job_app


@router.post("/track/finalize", response_model=JobApplicationResponse)
async def track_finalize_job(
    request: FinalizeJobRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Finalize job application with final result."""
    job_app = get_job_application(db, request.job_id, current_user.id)
    if not job_app:
        raise HTTPException(status_code=404, detail="Job application not found")

    job_app = finalize_job_application(
        db=db,
        job_app=job_app,
        hired=request.hired,
        weighted_score=request.weighted_score,
    )
    return job_app


@router.get("/history", response_model=list[JobApplicationResponse])
async def get_job_history(
    status_filter: Optional[str] = None,  # "passed", "rejected", "in_progress"
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's job application history."""
    query = db.query(JobApplication).filter(JobApplication.user_id == current_user.id)

    if status_filter == "passed":
        query = query.filter(JobApplication.final_hired == True)
    elif status_filter == "rejected":
        query = query.filter(
            JobApplication.completed == True, JobApplication.final_hired == False
        )
    elif status_filter == "in_progress":
        query = query.filter(JobApplication.completed == False)

    jobs = (
        query.order_by(JobApplication.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jobs


@router.get("/history/{job_id}", response_model=JobApplicationResponse)
async def get_job_details(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get details of a specific job application."""
    job = (
        db.query(JobApplication)
        .filter(
            JobApplication.id == job_id, JobApplication.user_id == current_user.id
        )
        .first()
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job application not found",
        )

    return job


@router.get("/stats", response_model=JobStatsResponse)
async def get_job_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's job application statistics."""
    total = (
        db.query(JobApplication)
        .filter(JobApplication.user_id == current_user.id)
        .count()
    )

    completed = (
        db.query(JobApplication)
        .filter(
            JobApplication.user_id == current_user.id,
            JobApplication.completed == True,
        )
        .count()
    )

    successful = (
        db.query(JobApplication)
        .filter(
            JobApplication.user_id == current_user.id,
            JobApplication.final_hired == True,
        )
        .count()
    )

    # Stats by difficulty
    by_difficulty = {}
    for difficulty in ["easy", "medium", "hard"]:
        diff_total = (
            db.query(JobApplication)
            .filter(
                JobApplication.user_id == current_user.id,
                JobApplication.difficulty == difficulty,
            )
            .count()
        )
        diff_passed = (
            db.query(JobApplication)
            .filter(
                JobApplication.user_id == current_user.id,
                JobApplication.difficulty == difficulty,
                JobApplication.final_hired == True,
            )
            .count()
        )
        by_difficulty[difficulty] = {"total": diff_total, "passed": diff_passed}

    success_rate = (successful / completed * 100) if completed > 0 else 0.0

    return JobStatsResponse(
        total_simulations=total,
        completed_simulations=completed,
        successful_simulations=successful,
        success_rate=round(success_rate, 1),
        by_difficulty=by_difficulty,
    )
