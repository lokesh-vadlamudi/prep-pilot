from __future__ import annotations

import unittest
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import mock, service, tutor
from app.models import Attempt, Card, Concept, User


def test_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def add_user(session: Session) -> User:
    user = User(username="learner", password_hash="test", level="newgrad", lang="python")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def add_concept(session: Session, slug: str, difficulty: str = "intro") -> Concept:
    concept = Concept(
        slug=slug,
        track="DSA",
        title=slug.replace("-", " ").title(),
        difficulty=difficulty,
        summary=f"Understand {slug}.",
        audience="newgrad",
    )
    session.add(concept)
    session.commit()
    session.refresh(concept)
    return concept


class AdaptiveLearningTests(unittest.TestCase):
    def test_low_accuracy_and_due_reviews_reduce_new_load(self):
        with test_session() as session:
            user = add_user(session)
            weak = add_concept(session, "hash-map-basics")
            unseen = add_concept(session, "two-pointers", "core")

            due_cards = []
            for index in range(5):
                card = Card(
                    user_id=user.id,
                    concept_id=weak.id,
                    prompt=f"Recall check {index}",
                    introduced=True,
                    due_date=date.today(),
                )
                session.add(card)
                due_cards.append(card)
            session.add(Card(
                user_id=user.id,
                concept_id=unseen.id,
                prompt="Explain two pointers",
                introduced=False,
            ))
            session.commit()

            for index, card in enumerate(due_cards):
                session.add(Attempt(
                    user_id=user.id,
                    card_id=card.id,
                    concept_id=weak.id,
                    track="DSA",
                    grade=4 if index == 0 else 1,
                    correct=index == 0,
                ))
            session.commit()

            plan = service.build_daily_plan(session, user)
            recommendation = service.build_learn_next(session, user)

            self.assertEqual(plan["adaptive"]["new_topic_limit"], 1)
            self.assertEqual(len(plan["new"]), 1)
            self.assertEqual(recommendation["mode"], "recover")
            self.assertEqual(recommendation["action"]["kind"], "review_session")
            self.assertEqual(recommendation["signals"]["recent_accuracy"], 0.2)
            self.assertEqual(recommendation["up_next"]["title"], "Two Pointers")

    def test_clear_queue_selects_intro_before_core(self):
        with test_session() as session:
            user = add_user(session)
            practiced = add_concept(session, "arrays")
            core = add_concept(session, "dynamic-programming", "core")
            intro = add_concept(session, "linked-lists", "intro")
            reviewed = Card(
                user_id=user.id,
                concept_id=practiced.id,
                introduced=True,
                due_date=date.today() + timedelta(days=3),
            )
            session.add(reviewed)
            session.add(Card(user_id=user.id, concept_id=core.id, introduced=False))
            session.add(Card(user_id=user.id, concept_id=intro.id, introduced=False))
            session.commit()
            for _ in range(5):
                session.add(Attempt(
                    user_id=user.id,
                    card_id=reviewed.id,
                    concept_id=practiced.id,
                    track="DSA",
                    grade=5,
                    correct=True,
                ))
            session.commit()

            recommendation = service.build_learn_next(session, user)

            self.assertEqual(recommendation["mode"], "learn")
            self.assertEqual(recommendation["concept"]["title"], "Linked Lists")
            self.assertEqual(recommendation["concept"]["mastery_state"], "Unseen")
            self.assertEqual(recommendation["signals"]["new_topic_limit"], 3)


class DgxDiagnosisTests(unittest.IsolatedAsyncioTestCase):
    async def test_dgx_interprets_but_does_not_replace_plan(self):
        model_result = {
            "diagnosis": "The learner recognizes the structure but misses the invariant.",
            "teaching_focus": "State the invariant before tracing.",
            "check_question": "What remains true after each iteration?",
        }
        with patch("app.tutor.chat_json", new=AsyncMock(return_value=model_result)):
            result = await tutor.diagnose_learning_plan(
                {"title": "Clear your due reviews", "action": {"kind": "review_session"}},
                [{"concept": "Two pointers", "correct": False}],
                learner="Explain from first principles.",
            )

        self.assertTrue(result["available"])
        self.assertEqual(result["teaching_focus"], model_result["teaching_focus"])
        self.assertNotIn("action", result)


class MockInterviewScoringTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_interview_is_not_scored_by_llm(self):
        transcript = [
            {"role": "interviewer", "content": "Tell me about your approach."},
            {"role": "candidate", "content": "   "},
        ]

        with patch("app.mock.chat_json", new=AsyncMock()) as scorer:
            result = await mock.score("coding", "arrays", transcript)

        scorer.assert_not_awaited()
        self.assertEqual(result["overall"], 0)
        self.assertEqual(result["verdict"], "not evaluated")
        self.assertEqual(result["strengths"], [])
        self.assertTrue(all(item["score"] == 0 for item in result["dimensions"]))

    async def test_candidate_response_is_scored_normally(self):
        transcript = [
            {"role": "interviewer", "content": "Tell me about your approach."},
            {"role": "candidate", "content": "I would start with a hash map."},
        ]
        expected = {"overall": 3, "verdict": "hire", "dimensions": []}

        with patch("app.mock.chat_json", new=AsyncMock(return_value=expected)) as scorer:
            result = await mock.score("coding", "arrays", transcript)

        scorer.assert_awaited_once()
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
