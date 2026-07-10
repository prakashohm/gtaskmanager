from __future__ import annotations

from datetime import date, timedelta

from app.models import GeneratedQuestion, TopicProgress
from app.services.dedup import (
    filter_novel_questions,
    normalize_question_text,
    question_text_hash,
    recent_question_hashes,
)
from app.services.math_templates import generate_math_questions, supports_math_topic
from app.services.progress import (
    apply_hysteresis,
    difficulty_from_success_rate,
    resolve_topic_difficulty,
    weighted_success_rate,
)
from app.services.question_counts import compute_topic_question_counts
from app.services.generator import subjects_needing_generation


def test_normalize_and_hash_stable():
    a = "What is the area of a 4 x 5 rectangle?"
    b = "  what is the area of a 4x5 rectangle?! "
    assert normalize_question_text(a) == normalize_question_text(b)
    assert question_text_hash(a) == question_text_hash(b)


def test_filter_novel_questions_drops_duplicates():
    known = recent_question_hashes(["Find the area of a 3 by 4 rectangle."])
    qs = [
        GeneratedQuestion(
            subject="Math",
            topic="calculating area",
            difficulty_level="maintained",
            question_text="Find the area of a 3 by 4 rectangle.",
            expected_answer="12",
        ),
        GeneratedQuestion(
            subject="Math",
            topic="calculating area",
            difficulty_level="maintained",
            question_text="A rug is 6 feet by 2 feet. What is the area?",
            expected_answer="12",
        ),
        GeneratedQuestion(
            subject="Math",
            topic="calculating area",
            difficulty_level="maintained",
            question_text="A rug is 6 feet by 2 feet. What is the area?",
            expected_answer="12",
        ),
    ]
    kept = filter_novel_questions(qs, known)
    assert len(kept) == 1
    assert "rug" in kept[0].question_text.lower()


def test_difficulty_thresholds():
    assert difficulty_from_success_rate(0) == "simplified"
    assert difficulty_from_success_rate(59.9) == "simplified"
    assert difficulty_from_success_rate(60) == "maintained"
    assert difficulty_from_success_rate(80) == "maintained"
    assert difficulty_from_success_rate(80.1) == "increased"


def test_weighted_success_rate_prefers_recent():
    today = date(2026, 7, 10)
    entries = [
        {"entry_date": (today - timedelta(days=6)).isoformat(), "is_correct": True},
        {"entry_date": (today - timedelta(days=6)).isoformat(), "is_correct": True},
        {"entry_date": today.isoformat(), "is_correct": False},
        {"entry_date": today.isoformat(), "is_correct": False},
    ]
    rate, _, _ = weighted_success_rate(entries, today=today, decay=0.5)
    # Recent misses should pull the rate well below 50%.
    assert rate < 40.0


def test_adaptive_question_counts_favor_struggling_topics():
    progress = [
        TopicProgress(
            subject="Math",
            topic="calculating area",
            attempts=10,
            correct=3,
            success_rate=30,
            recommended_difficulty="simplified",
        ),
        TopicProgress(
            subject="Math",
            topic="unit price",
            attempts=10,
            correct=9,
            success_rate=90,
            recommended_difficulty="increased",
        ),
    ]
    counts = compute_topic_question_counts(progress, 10, adaptive=True)
    assert counts["Math::calculating area"] > counts["Math::unit price"]
    assert sum(counts.values()) == 10
    assert all(v >= 1 for v in counts.values())


def test_even_split_when_adaptive_disabled():
    progress = [
        TopicProgress(subject="Math", topic="a", recommended_difficulty="simplified"),
        TopicProgress(subject="Math", topic="b", recommended_difficulty="increased"),
    ]
    counts = compute_topic_question_counts(progress, 10, adaptive=False)
    assert counts["Math::a"] == 5
    assert counts["Math::b"] == 5


def test_math_templates_produce_unique_signatures():
    assert supports_math_topic("calculating area")
    qs = generate_math_questions(
        student_id="guhan",
        question_date="2026-07-10",
        topic="calculating area",
        difficulty="maintained",
        count=5,
    )
    assert len(qs) == 5
    texts = {q.question_text for q in qs}
    assert len(texts) == 5
    for q in qs:
        assert q.expected_answer
        assert q.scaffolding_hints


def test_math_templates_day_stable():
    a = generate_math_questions(
        student_id="guhan",
        question_date="2026-07-10",
        topic="unit price",
        difficulty="simplified",
        count=3,
    )
    b = generate_math_questions(
        student_id="guhan",
        question_date="2026-07-10",
        topic="unit price",
        difficulty="simplified",
        count=3,
    )
    c = generate_math_questions(
        student_id="guhan",
        question_date="2026-07-11",
        topic="unit price",
        difficulty="simplified",
        count=3,
    )
    assert [q.question_text for q in a] == [q.question_text for q in b]
    assert [q.question_text for q in a] != [q.question_text for q in c]


def test_hysteresis_holds_within_margin():
    # 62% clears the raw 60% threshold but not the 65% hysteresis bar, so a
    # topic currently at "simplified" should stay there rather than flip daily.
    difficulty, changed, rationale = apply_hysteresis("maintained", "simplified", 62.0, margin=5.0)
    assert difficulty == "simplified"
    assert changed is False
    assert "short" in rationale.lower()


def test_hysteresis_releases_past_margin():
    difficulty, changed, rationale = apply_hysteresis("maintained", "simplified", 66.0, margin=5.0)
    assert difficulty == "maintained"
    assert changed is True
    assert "moved" in rationale.lower()


def test_hysteresis_first_run_has_no_prior_state():
    difficulty, changed, rationale = apply_hysteresis("increased", None, 90.0, margin=5.0)
    assert difficulty == "increased"
    assert changed is True
    assert rationale == ""


def test_pin_overrides_recommendation():
    # A weak recent rate would normally hold/return "simplified", but a parent
    # pin to "increased" must win outright and skip hysteresis entirely.
    difficulty, changed, rationale = resolve_topic_difficulty(
        "simplified", "increased", 40.0, pin="increased", margin=5.0
    )
    assert difficulty == "increased"
    assert changed is False
    assert rationale == "Pinned by parent."


def test_subjects_needing_generation():
    progress = [
        TopicProgress(subject="Math", topic="calculating area"),
        TopicProgress(subject="Reading", topic="identifying theme"),
    ]
    existing = [{"subject": "Math", "question_text": "x"}]
    needing = subjects_needing_generation(existing, progress, None)
    assert needing == ["Reading"]
    assert subjects_needing_generation(existing, progress, ["Math"]) == []
