from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, Set

from app.models import DifficultyLevel, GeneratedQuestion
from app.services.dedup import param_signature_hash


@dataclass(frozen=True)
class MathSpec:
    subject: str
    topic: str
    difficulty_level: DifficultyLevel
    question_text: str
    scaffolding_hints: List[str]
    expected_answer: str
    signature: str


def _rng(student_id: str, question_date: str, topic: str, index: int) -> random.Random:
    seed_material = f"{student_id}|{question_date}|{topic}|{index}".encode("utf-8")
    seed = int(hashlib.sha256(seed_material).hexdigest()[:16], 16)
    return random.Random(seed)


def _area_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    if difficulty == "simplified":
        length = rng.randint(2, 8)
        width = rng.randint(2, 6)
        answer = length * width
        return MathSpec(
            subject="Math",
            topic="calculating area",
            difficulty_level=difficulty,
            question_text=(
                f"A rectangle is {length} feet long and {width} feet wide. "
                f"What is the area in square feet?"
            ),
            scaffolding_hints=[
                "Area of a rectangle = length × width.",
                f"Multiply {length} × {width}.",
            ],
            expected_answer=str(answer),
            signature=f"rect:{length}x{width}",
        )

    if difficulty == "increased":
        shape = rng.choice(["rectangle", "triangle"])
        if shape == "rectangle":
            length = rng.randint(8, 18)
            width = rng.randint(5, 12)
            # One extra step: find area after adding a border strip conceptually
            border = rng.randint(1, 2)
            outer_l = length + border
            outer_w = width + border
            answer = outer_l * outer_w
            return MathSpec(
                subject="Math",
                topic="calculating area",
                difficulty_level=difficulty,
                question_text=(
                    f"A garden is {length} meters long and {width} meters wide. "
                    f"A path {border} meter(s) wide is added around all sides. "
                    f"What is the area of the larger rectangle in square meters?"
                ),
                scaffolding_hints=[
                    "New length = old length + border on both ends.",
                    f"New length = {length} + {border} + {border} = {outer_l}.",
                    f"New width = {width} + {border} + {border} = {outer_w}.",
                    "Area = new length × new width.",
                ],
                expected_answer=str(answer),
                signature=f"border-rect:{length}x{width}+{border}",
            )
        base = rng.choice([6, 8, 10, 12, 14])
        height = rng.choice([3, 4, 5, 6, 7, 8])
        answer = (base * height) // 2
        return MathSpec(
            subject="Math",
            topic="calculating area",
            difficulty_level=difficulty,
            question_text=(
                f"A triangle has a base of {base} centimeters and a height of {height} centimeters. "
                f"What is the area in square centimeters?"
            ),
            scaffolding_hints=[
                "Area of a triangle = (base × height) ÷ 2.",
                f"First multiply {base} × {height}, then divide by 2.",
            ],
            expected_answer=str(answer),
            signature=f"tri:{base}x{height}",
        )

    # maintained
    shape = rng.choice(["rectangle", "triangle"])
    if shape == "rectangle":
        length = rng.randint(4, 14)
        width = rng.randint(3, 10)
        answer = length * width
        return MathSpec(
            subject="Math",
            topic="calculating area",
            difficulty_level=difficulty,
            question_text=(
                f"A classroom rug is {length} feet long and {width} feet wide. "
                f"What is the area of the rug in square feet?"
            ),
            scaffolding_hints=[
                "Area of a rectangle = length × width.",
                f"Multiply {length} × {width}.",
            ],
            expected_answer=str(answer),
            signature=f"rect:{length}x{width}",
        )
    base = rng.choice([4, 6, 8, 10, 12])
    height = rng.choice([2, 3, 4, 5, 6])
    answer = (base * height) // 2
    return MathSpec(
        subject="Math",
        topic="calculating area",
        difficulty_level=difficulty,
        question_text=(
            f"A triangular flag has a base of {base} inches and a height of {height} inches. "
            f"What is the area in square inches?"
        ),
        scaffolding_hints=[
            "Area of a triangle = (base × height) ÷ 2.",
            f"Compute ({base} × {height}) ÷ 2.",
        ],
        expected_answer=str(answer),
        signature=f"tri:{base}x{height}",
    )


def _unit_price_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    if difficulty == "simplified":
        pack = rng.choice([2, 4, 5, 10])
        unit = rng.choice([2, 3, 4, 5])
        total = pack * unit
        return MathSpec(
            subject="Math",
            topic="unit price",
            difficulty_level=difficulty,
            question_text=(
                f"A pack of {pack} pencils costs ${total}. "
                f"What is the cost of one pencil in dollars?"
            ),
            scaffolding_hints=[
                "Unit price = total cost ÷ number of items.",
                f"Divide {total} by {pack}.",
            ],
            expected_answer=str(unit),
            signature=f"pack:{pack}@{total}",
        )

    if difficulty == "increased":
        pack = rng.choice([6, 8, 12])
        unit_cents = rng.choice([25, 50, 75, 125, 150])
        total_cents = pack * unit_cents
        total_dollars = total_cents / 100.0
        unit_dollars = unit_cents / 100.0
        # Prefer clean dollar strings
        total_str = f"{total_dollars:.2f}".rstrip("0").rstrip(".")
        unit_str = f"{unit_dollars:.2f}".rstrip("0").rstrip(".")
        return MathSpec(
            subject="Math",
            topic="unit price",
            difficulty_level=difficulty,
            question_text=(
                f"A box of {pack} markers costs ${total_str}. "
                f"What is the unit price for one marker in dollars?"
            ),
            scaffolding_hints=[
                "Unit price = total cost ÷ number of items.",
                f"Divide {total_str} by {pack}.",
                "Write the answer as a dollar amount (for example 1.25).",
            ],
            expected_answer=unit_str,
            signature=f"pack:{pack}@{total_str}",
        )

    pack = rng.choice([3, 4, 5, 6, 8])
    unit = rng.choice([2, 3, 4, 5, 6, 7])
    total = pack * unit
    item = rng.choice(["apples", "erasers", "stickers", "notebooks"])
    return MathSpec(
        subject="Math",
        topic="unit price",
        difficulty_level=difficulty,
        question_text=(
            f"A bag of {pack} {item} costs ${total}. "
            f"What is the cost of one item in dollars?"
        ),
        scaffolding_hints=[
            "Unit price = total cost ÷ number of items.",
            f"Divide {total} by {pack}.",
        ],
        expected_answer=str(unit),
        signature=f"pack:{pack}@{total}:{item}",
    )


_TOPIC_BUILDERS = {
    "calculating area": _area_specs,
    "unit price": _unit_price_specs,
}


def supports_math_topic(topic: str) -> bool:
    return topic.strip().lower() in _TOPIC_BUILDERS


def generate_math_questions(
    *,
    student_id: str,
    question_date: date | str,
    topic: str,
    difficulty: DifficultyLevel,
    count: int,
    used_signatures: Optional[Set[str]] = None,
) -> List[GeneratedQuestion]:
    """Build parametric math questions with day-stable RNG and signature dedup."""
    builder = _TOPIC_BUILDERS.get(topic.strip().lower())
    if not builder or count <= 0:
        return []

    date_str = question_date.isoformat() if isinstance(question_date, date) else str(question_date)
    used = set(used_signatures or set())
    questions: List[GeneratedQuestion] = []

    # Try more slots than needed so we can skip recently used signatures.
    for index in range(count * 8):
        if len(questions) >= count:
            break
        spec = builder(_rng(student_id, date_str, topic, index), difficulty)
        sig_hash = param_signature_hash(topic, spec.signature)
        if sig_hash in used:
            continue
        used.add(sig_hash)
        questions.append(
            GeneratedQuestion(
                subject=spec.subject,
                topic=topic,
                difficulty_level=spec.difficulty_level,
                question_text=spec.question_text,
                scaffolding_hints=spec.scaffolding_hints,
                expected_answer=spec.expected_answer,
            )
        )
    return questions


def collect_used_math_signatures(
    recent_texts: Sequence[str],
    topics: Sequence[str],
) -> Set[str]:
    """
    Best-effort: hash recent question texts as signatures so parametric
    regeneration avoids identical wording even across template versions.
    """
    used: Set[str] = set()
    for topic in topics:
        for text in recent_texts:
            used.add(param_signature_hash(topic, text))
    return used
