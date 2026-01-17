from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class JobApplicationResponse(BaseModel):
    id: int
    job_source: str
    company: str
    role: str
    difficulty: str
    location: Optional[str]

    screening_passed: Optional[bool]
    screening_feedback: Optional[str]

    technical_passed: Optional[bool]
    technical_score: Optional[float]
    technical_details: Optional[Any]

    behavioral_passed: Optional[bool]
    behavioral_score: Optional[float]
    behavioral_feedback: Optional[str]

    final_hired: Optional[bool]
    final_weighted_score: Optional[float]

    completed: bool
    current_stage: str

    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class JobStatsResponse(BaseModel):
    total_simulations: int
    completed_simulations: int
    successful_simulations: int  # Jobs "gotten into"
    success_rate: float
    by_difficulty: dict[str, dict[str, int]]  # {easy: {total: 5, passed: 3}, ...}
