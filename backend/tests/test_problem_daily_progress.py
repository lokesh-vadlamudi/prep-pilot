from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import DayLog, Problem, ProblemStatus, Settings, User
from app.routers.problem_routes import StatusIn, set_status, target_status


def memory_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class DailyCodingProgressTests(unittest.TestCase):
    def test_marking_problem_solved_updates_daily_target(self):
        with memory_session() as session:
            user = User(username="pilot", password_hash="x")
            problem = Problem(slug="two-sum", title="Two Sum", category="Arrays & Hashing")
            session.add(user)
            session.add(problem)
            session.commit()
            session.refresh(user)
            session.refresh(problem)
            session.add(Settings(user_id=user.id, daily_problem_target=2))
            session.commit()

            set_status(problem.id, StatusIn(status="solved", confidence=2), user, session)
            result = target_status(user, session)

            self.assertEqual(result["solved_today"], 1)
            self.assertFalse(result["target_met_today"])
            log = session.exec(
                select(DayLog).where(DayLog.user_id == user.id, DayLog.day == date.today())
            ).one()
            self.assertEqual(log.coding_solved, 1)

            set_status(problem.id, StatusIn(status="todo"), user, session)
            reset = target_status(user, session)
            self.assertEqual(reset["solved_today"], 0)
            self.assertFalse(reset["target_met_today"])

            set_status(problem.id, StatusIn(status="solved", confidence=2), user, session)
            self.assertEqual(target_status(user, session)["solved_today"], 1)

    def test_daily_target_uses_local_daylog_not_utc_touch_date(self):
        with memory_session() as session:
            user = User(username="pilot", password_hash="x")
            problem = Problem(slug="valid-anagram", title="Valid Anagram", category="Arrays & Hashing")
            session.add(user)
            session.add(problem)
            session.commit()
            session.refresh(user)
            session.refresh(problem)
            session.add(Settings(user_id=user.id, daily_problem_target=1))
            session.add(DayLog(user_id=user.id, day=date.today(), coding_solved=1))
            session.add(ProblemStatus(
                user_id=user.id,
                problem_id=problem.id,
                status="solved",
                solved_date=date.today(),
                # Simulates an evening Pacific solve whose naive UTC date is tomorrow.
                last_touched=datetime.combine(date.today() + timedelta(days=1), datetime.min.time()),
            ))
            session.commit()

            result = target_status(user, session)

            self.assertEqual(result["solved_today"], 1)
            self.assertTrue(result["target_met_today"])


if __name__ == "__main__":
    unittest.main()
