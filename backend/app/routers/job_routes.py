"""Manual job-application tracking, daily goals, and follow-up reminders."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import RequireUser
from ..db import get_session
from ..models import JobApplication, Settings, User, utcnow

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[RequireUser])

STATUSES = ("saved", "applied", "interview", "offer", "rejected", "withdrawn")
ACTIVE_STATUSES = ("saved", "applied", "interview")


class JobCreate(BaseModel):
    company: str
    role: str
    job_url: str = ""
    location: str = ""
    status: str = "applied"
    applied_date: Optional[date] = None
    follow_up_date: Optional[date] = None
    notes: str = ""


class JobUpdate(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    job_url: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    applied_date: Optional[date] = None
    follow_up_date: Optional[date] = None
    notes: Optional[str] = None


class TargetUpdate(BaseModel):
    daily_target: int


def _clean_required(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(400, f"{label} is required")
    if len(value) > 160:
        raise HTTPException(400, f"{label} is too long")
    return value


def _validate_status(value: str) -> str:
    value = value.strip().lower()
    if value not in STATUSES:
        raise HTTPException(400, "Invalid application status")
    return value


def _settings(session: Session, user_id: int) -> Settings:
    value = session.exec(select(Settings).where(Settings.user_id == user_id)).first()
    if not value:
        value = Settings(user_id=user_id)
        session.add(value)
        session.commit()
        session.refresh(value)
    return value


def _owned_job(session: Session, user_id: int, job_id: int) -> JobApplication:
    value = session.exec(
        select(JobApplication).where(
            JobApplication.id == job_id, JobApplication.user_id == user_id
        )
    ).first()
    if not value:
        raise HTTPException(404, "Job application not found")
    return value


def _job_out(job: JobApplication) -> dict:
    return {
        "id": job.id,
        "company": job.company,
        "role": job.role,
        "job_url": job.job_url,
        "location": job.location,
        "status": job.status,
        "applied_date": job.applied_date,
        "follow_up_date": job.follow_up_date,
        "notes": job.notes,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("")
def dashboard(user: User = RequireUser, session: Session = Depends(get_session)):
    jobs = session.exec(
        select(JobApplication)
        .where(JobApplication.user_id == user.id)
        .order_by(JobApplication.updated_at.desc())
    ).all()
    today = date.today()
    target = max(1, _settings(session, user.id).daily_application_target)
    applied_today = sum(job.applied_date == today for job in jobs)
    due = [
        _job_out(job) for job in jobs
        if job.status in ACTIVE_STATUSES
        and job.follow_up_date is not None
        and job.follow_up_date <= today
    ]
    counts = {status: sum(job.status == status for job in jobs) for status in STATUSES}
    return {
        "date": today,
        "daily_target": target,
        "applied_today": applied_today,
        "remaining_today": max(0, target - applied_today),
        "target_met": applied_today >= target,
        "follow_ups_due": due,
        "counts": counts,
        "jobs": [_job_out(job) for job in jobs],
    }


@router.post("")
def create_job(body: JobCreate, user: User = RequireUser,
               session: Session = Depends(get_session)):
    status = _validate_status(body.status)
    applied_date = body.applied_date
    if status != "saved" and applied_date is None:
        applied_date = date.today()
    job = JobApplication(
        user_id=user.id,
        company=_clean_required(body.company, "Company"),
        role=_clean_required(body.role, "Role"),
        job_url=body.job_url.strip()[:1000],
        location=body.location.strip()[:160],
        status=status,
        applied_date=applied_date,
        follow_up_date=body.follow_up_date,
        notes=body.notes.strip()[:5000],
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return _job_out(job)


@router.patch("/{job_id}")
def update_job(job_id: int, body: JobUpdate, user: User = RequireUser,
               session: Session = Depends(get_session)):
    job = _owned_job(session, user.id, job_id)
    fields = body.model_fields_set
    if "company" in fields and body.company is not None:
        job.company = _clean_required(body.company, "Company")
    if "role" in fields and body.role is not None:
        job.role = _clean_required(body.role, "Role")
    if "job_url" in fields:
        job.job_url = (body.job_url or "").strip()[:1000]
    if "location" in fields:
        job.location = (body.location or "").strip()[:160]
    if "notes" in fields:
        job.notes = (body.notes or "").strip()[:5000]
    if "follow_up_date" in fields:
        job.follow_up_date = body.follow_up_date
    if "applied_date" in fields:
        job.applied_date = body.applied_date
    if "status" in fields and body.status is not None:
        job.status = _validate_status(body.status)
        if job.status != "saved" and job.applied_date is None:
            job.applied_date = date.today()
    job.updated_at = utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return _job_out(job)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, user: User = RequireUser,
               session: Session = Depends(get_session)):
    job = _owned_job(session, user.id, job_id)
    session.delete(job)
    session.commit()
    return Response(status_code=204)


@router.put("/target/daily")
def update_target(body: TargetUpdate, user: User = RequireUser,
                  session: Session = Depends(get_session)):
    if not 1 <= body.daily_target <= 50:
        raise HTTPException(400, "Daily target must be between 1 and 50")
    value = _settings(session, user.id)
    value.daily_application_target = body.daily_target
    session.add(value)
    session.commit()
    return {"daily_target": value.daily_application_target}
