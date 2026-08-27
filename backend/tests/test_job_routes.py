from __future__ import annotations

import unittest
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import JobApplication, User
from app.routers import job_routes


def test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def add_user(session: Session, name: str) -> User:
    user = User(username=name, password_hash="test")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class JobTrackerTests(unittest.TestCase):
    def test_manual_application_counts_toward_daily_target(self):
        with test_session() as session:
            user = add_user(session, "pilot")
            job_routes.create_job(
                job_routes.JobCreate(company="Acme", role="Software Engineer"),
                user=user,
                session=session,
            )

            result = job_routes.dashboard(user=user, session=session)

            self.assertEqual(result["applied_today"], 1)
            self.assertEqual(result["remaining_today"], 4)
            self.assertEqual(result["jobs"][0]["company"], "Acme")

    def test_saved_lead_does_not_count_until_applied(self):
        with test_session() as session:
            user = add_user(session, "pilot")
            created = job_routes.create_job(
                job_routes.JobCreate(company="Northstar", role="Backend", status="saved"),
                user=user,
                session=session,
            )
            self.assertEqual(job_routes.dashboard(user=user, session=session)["applied_today"], 0)

            job_routes.update_job(
                created["id"], job_routes.JobUpdate(status="applied"), user=user, session=session,
            )

            self.assertEqual(job_routes.dashboard(user=user, session=session)["applied_today"], 1)

    def test_due_follow_up_is_reminded_and_user_data_is_isolated(self):
        with test_session() as session:
            owner = add_user(session, "owner")
            stranger = add_user(session, "stranger")
            job_routes.create_job(
                job_routes.JobCreate(
                    company="Orbit",
                    role="Platform Engineer",
                    follow_up_date=date.today() - timedelta(days=1),
                ),
                user=owner,
                session=session,
            )

            self.assertEqual(len(job_routes.dashboard(user=owner, session=session)["follow_ups_due"]), 1)
            self.assertEqual(job_routes.dashboard(user=stranger, session=session)["jobs"], [])
            with self.assertRaises(HTTPException) as error:
                job_routes.update_job(1, job_routes.JobUpdate(status="offer"), user=stranger, session=session)
            self.assertEqual(error.exception.status_code, 404)

    def test_daily_target_is_customizable(self):
        with test_session() as session:
            user = add_user(session, "pilot")
            result = job_routes.update_target(
                job_routes.TargetUpdate(daily_target=8), user=user, session=session,
            )
            self.assertEqual(result["daily_target"], 8)
            self.assertEqual(job_routes.dashboard(user=user, session=session)["daily_target"], 8)

            with self.assertRaises(HTTPException):
                job_routes.update_target(
                    job_routes.TargetUpdate(daily_target=0), user=user, session=session,
                )


if __name__ == "__main__":
    unittest.main()
