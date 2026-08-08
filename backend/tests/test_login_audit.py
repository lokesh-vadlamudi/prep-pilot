from __future__ import annotations

import unittest
from datetime import date, datetime

from fastapi import HTTPException, Response
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth
from app.models import (Attempt, Card, Concept, ConceptStatus, DayLog,
                        LoginAudit, MockSession, Problem, ProblemStatus, User)
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

    def test_admin_summary_includes_progress_without_sensitive_content(self):
        with memory_session() as session:
            admin = User(username="admin", password_hash="secret", is_admin=True)
            learner = User(username="learner", password_hash="hidden", level="newgrad")
            session.add(admin); session.add(learner); session.commit(); session.refresh(admin); session.refresh(learner)
            concept = Concept(slug="queues", track="DSA", title="Queues")
            problem = Problem(slug="two-sum", title="Two Sum", category="Array")
            session.add(concept); session.add(problem); session.commit(); session.refresh(concept); session.refresh(problem)
            card = Card(user_id=learner.id, concept_id=concept.id, prompt="private prompt", last_reviewed=datetime.utcnow())
            session.add(card); session.commit(); session.refresh(card)
            session.add(Attempt(user_id=learner.id, card_id=card.id, concept_id=concept.id,
                                correct=True, user_answer="private answer"))
            session.add(DayLog(user_id=learner.id, day=date.today(), coding_solved=1))
            session.add(ProblemStatus(user_id=learner.id, problem_id=problem.id, status="solved"))
            session.add(ConceptStatus(user_id=learner.id, concept_id=concept.id, completed=True,
                                      completed_at=datetime.utcnow()))
            session.add(MockSession(user_id=learner.id, status="done", transcript_json='[{"private": true}]',
                                    ended_at=datetime.utcnow()))
            session.commit()

            row = next(item for item in login_audit(30, admin, session)["users"]
                       if item["username"] == "learner")
            self.assertEqual(row["level"], "newgrad")
            self.assertEqual(row["progress"]["study_days"], 1)
            self.assertEqual(row["progress"]["current_streak"], 1)
            self.assertEqual(row["progress"]["reviews"], 1)
            self.assertEqual(row["progress"]["accuracy"], 1.0)
            self.assertEqual(row["progress"]["problems_solved"], 1)
            self.assertEqual(row["progress"]["topics_completed"], 1)
            self.assertEqual(row["progress"]["mocks_completed"], 1)
            self.assertEqual(row["progress"]["cards_reviewed"], 1)
            self.assertNotIn("password_hash", row)
            self.assertNotIn("user_answer", str(row))


if __name__ == "__main__":
    unittest.main()
