from __future__ import annotations

import unittest
from datetime import date

from fastapi import HTTPException, Response
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth
from app.models import LoginAudit, User
from app.routers.auth_routes import LoginIn, login, login_audit, record_login_audit


def memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class LoginAuditTests(unittest.TestCase):
    def test_successful_login_is_recorded_but_failed_login_is_not(self):
        with memory_session() as session:
            user = User(username="learner", password_hash=auth.hash_password("correct-pass"))
            session.add(user); session.commit(); session.refresh(user)

            failed = login(LoginIn(username="learner", password="wrong-pass"), Response(), session)
            self.assertEqual(failed.status_code, 401)
            self.assertEqual(session.exec(select(LoginAudit)).all(), [])

            result = login(LoginIn(username="learner", password="correct-pass"), Response(), session)
            self.assertTrue(result["ok"])
            audits = session.exec(select(LoginAudit)).all()
            self.assertEqual([(row.user_id, row.event, row.day) for row in audits],
                             [(user.id, "login", date.today())])

    def test_daily_activity_is_deduplicated(self):
        with memory_session() as session:
            user = User(username="learner", password_hash="x")
            session.add(user); session.commit(); session.refresh(user)

            record_login_audit(session, user, "active")
            record_login_audit(session, user, "active")

            self.assertEqual(len(session.exec(select(LoginAudit)).all()), 1)

    def test_audit_summary_is_admin_only(self):
        with memory_session() as session:
            admin = User(username="admin", password_hash="x", is_admin=True)
            learner = User(username="learner", password_hash="x")
            session.add(admin); session.add(learner); session.commit(); session.refresh(admin); session.refresh(learner)
            record_login_audit(session, learner, "login")
            record_login_audit(session, learner, "active")

            with self.assertRaises(HTTPException) as caught:
                login_audit(30, learner, session)
            self.assertEqual(caught.exception.status_code, 403)

            summary = login_audit(30, admin, session)
            row = next(item for item in summary["users"] if item["username"] == "learner")
            self.assertEqual((row["login_days"], row["active_days"]), (1, 1))
            self.assertEqual(row["recent_active_dates"], [str(date.today())])


if __name__ == "__main__":
    unittest.main()
