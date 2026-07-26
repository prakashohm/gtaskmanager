from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Callable, List, Optional, Sequence, Set

from app.models import DifficultyLevel, GeneratedQuestion
from app.services.dedup import param_signature_hash

# Generic first nudge — never includes the arithmetic that gives the answer away.
_GENERIC_START = "What's the first step you'd try?"


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


def _money(n: float) -> str:
    text = f"{n:.2f}".rstrip("0").rstrip(".")
    return text


def _frac_str(num: int, den: int) -> str:
    f = Fraction(num, den)
    if f.denominator == 1:
        return str(f.numerator)
    return f"{f.numerator}/{f.denominator}"


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
            scaffolding_hints=[_GENERIC_START, "Unit price means total cost divided by how many items."],
            expected_answer=str(unit),
            signature=f"pack:{pack}@{total}",
        )

    if difficulty == "increased":
        pack = rng.choice([6, 8, 12])
        unit_cents = rng.choice([25, 50, 75, 125, 150])
        total_cents = pack * unit_cents
        total_dollars = total_cents / 100.0
        unit_dollars = unit_cents / 100.0
        total_str = _money(total_dollars)
        unit_str = _money(unit_dollars)
        return MathSpec(
            subject="Math",
            topic="unit price",
            difficulty_level=difficulty,
            question_text=(
                f"A box of {pack} markers costs ${total_str}. "
                f"What is the unit price for one marker in dollars?"
            ),
            scaffolding_hints=[
                _GENERIC_START,
                "Unit price means total cost divided by how many items.",
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
        scaffolding_hints=[_GENERIC_START, "Unit price means total cost divided by how many items."],
        expected_answer=str(unit),
        signature=f"pack:{pack}@{total}:{item}",
    )


def _arithmetic_word_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    name = rng.choice(["Maya", "Jordan", "Sam", "Alex", "Riley"])
    if difficulty == "simplified":
        a = rng.randint(12, 40)
        b = rng.randint(3, 15)
        op = rng.choice(["+", "-"])
        if op == "+":
            ans = a + b
            text = f"{name} has {a} stickers and gets {b} more. How many stickers does {name} have now?"
            sig = f"add:{a}+{b}"
        else:
            if b > a:
                a, b = b, a
            ans = a - b
            text = f"{name} has {a} points and loses {b}. How many points are left?"
            sig = f"sub:{a}-{b}"
        return MathSpec(
            subject="Math",
            topic="arithmetic word problems",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Decide whether you need to add or subtract."],
            expected_answer=str(ans),
            signature=sig,
        )

    if difficulty == "increased":
        a = rng.randint(8, 24)
        b = rng.randint(3, 9)
        c = rng.randint(2, 6)
        ans = a * b - c
        text = (
            f"{name} packs {a} boxes with {b} books each, then gives away {c} books. "
            f"How many books does {name} have left?"
        )
        return MathSpec(
            subject="Math",
            topic="arithmetic word problems",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[
                _GENERIC_START,
                "Do the multiplication first, then subtract what was given away.",
            ],
            expected_answer=str(ans),
            signature=f"mulsub:{a}*{b}-{c}",
        )

    a = rng.randint(4, 12)
    b = rng.randint(3, 9)
    ans = a * b
    item = rng.choice(["muffins", "cards", "marbles", "pens"])
    text = f"{name} buys {a} packs of {item}. Each pack has {b}. How many {item} in all?"
    return MathSpec(
        subject="Math",
        topic="arithmetic word problems",
        difficulty_level=difficulty,
        question_text=text,
        scaffolding_hints=[_GENERIC_START, "Think about equal groups — multiply."],
        expected_answer=str(ans),
        signature=f"mul:{a}*{b}:{item}",
    )


def _fractions_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    if difficulty == "simplified":
        den = rng.choice([2, 3, 4, 5, 6, 8])
        a = rng.randint(1, den - 1)
        b = rng.randint(1, den - a) if den - a >= 1 else 1
        if a + b >= den:
            b = max(1, den - a - 1) if den - a > 1 else 1
        ans = _frac_str(a + b, den)
        text = (
            f"You eat {a}/{den} of a pizza and a friend eats {b}/{den} of the same pizza. "
            f"What fraction of the pizza did you eat together? (Simplify if you can.)"
        )
        return MathSpec(
            subject="Math",
            topic="fractions",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Same denominator — add the numerators."],
            expected_answer=ans,
            signature=f"fadd:{a}/{den}+{b}/{den}",
        )

    if difficulty == "increased":
        a, b = rng.choice([(1, 2), (1, 3), (2, 3), (3, 4), (2, 5)])
        c, d = rng.choice([(1, 4), (1, 3), (1, 5), (2, 5), (1, 6)])
        # Prefer multiplication of fractions for a clean skill
        result = Fraction(a, b) * Fraction(c, d)
        ans = _frac_str(result.numerator, result.denominator)
        text = (
            f"A recipe needs {a}/{b} cup of sugar. You make {c}/{d} of the recipe. "
            f"How much sugar do you need? Answer as a simplified fraction."
        )
        return MathSpec(
            subject="Math",
            topic="fractions",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[
                _GENERIC_START,
                "Multiply the fractions: numerators together, denominators together, then simplify.",
            ],
            expected_answer=ans,
            signature=f"fmul:{a}/{b}*{c}/{d}",
        )

    den = rng.choice([4, 5, 6, 8, 10])
    a = rng.randint(1, den - 1)
    whole = rng.randint(2, 5)
    result = Fraction(a, den) * whole
    ans = _frac_str(result.numerator, result.denominator)
    text = (
        f"Each bottle holds {a}/{den} liter. You have {whole} bottles. "
        f"How many liters in total? Answer as a simplified fraction or whole number."
    )
    return MathSpec(
        subject="Math",
        topic="fractions",
        difficulty_level=difficulty,
        question_text=text,
        scaffolding_hints=[_GENERIC_START, "Multiply the fraction by the whole number."],
        expected_answer=ans,
        signature=f"fscale:{a}/{den}*{whole}",
    )


def _percentages_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    if difficulty == "simplified":
        pct = rng.choice([10, 20, 25, 50])
        base = rng.choice([40, 60, 80, 100, 120, 200])
        ans = int(base * pct / 100)
        text = f"What is {pct}% of {base}?"
        return MathSpec(
            subject="Math",
            topic="percentages",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Percent means 'out of 100' — try 10% first if it helps."],
            expected_answer=str(ans),
            signature=f"pct:{pct}%*{base}",
        )

    if difficulty == "increased":
        pct = rng.choice([15, 20, 25, 30])
        price = rng.choice([40, 60, 80, 120, 160])
        discount = price * pct / 100
        ans = _money(price - discount)
        text = (
            f"A hoodie costs ${price}. It is {pct}% off. "
            f"What is the sale price in dollars?"
        )
        return MathSpec(
            subject="Math",
            topic="percentages",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[
                _GENERIC_START,
                "Find the discount amount first, then subtract it from the original price.",
            ],
            expected_answer=ans,
            signature=f"sale:{price}-{pct}%",
        )

    pct = rng.choice([10, 15, 20, 25])
    bill = rng.choice([20, 40, 50, 80])
    tip = bill * pct / 100
    ans = _money(tip)
    text = f"A meal costs ${bill}. You leave a {pct}% tip. How much is the tip in dollars?"
    return MathSpec(
        subject="Math",
        topic="percentages",
        difficulty_level=difficulty,
        question_text=text,
        scaffolding_hints=[_GENERIC_START, "Tip = percent of the bill."],
        expected_answer=ans,
        signature=f"tip:{bill}@{pct}%",
    )


def _order_of_operations_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    if difficulty == "simplified":
        a = rng.randint(2, 9)
        b = rng.randint(2, 6)
        c = rng.randint(1, 8)
        ans = a + b * c
        text = (
            f"Evaluate: {a} + {b} × {c}. "
            f"(Remember multiplication before addition.)"
        )
        return MathSpec(
            subject="Math",
            topic="order of operations",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Do multiplication before addition (PEMDAS)."],
            expected_answer=str(ans),
            signature=f"pemdas:{a}+{b}*{c}",
        )

    if difficulty == "increased":
        a = rng.randint(2, 6)
        b = rng.randint(2, 5)
        c = rng.randint(2, 4)
        d = rng.randint(1, 5)
        ans = (a + b) * c - d
        text = f"Evaluate: ({a} + {b}) × {c} − {d}."
        return MathSpec(
            subject="Math",
            topic="order of operations",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Parentheses first, then multiply, then subtract."],
            expected_answer=str(ans),
            signature=f"pemdas:({a}+{b})*{c}-{d}",
        )

    a = rng.randint(3, 9)
    b = rng.randint(2, 5)
    c = rng.randint(2, 6)
    ans = a * b + c
    text = (
        f"A game gives {a} points per level for {b} levels, then a bonus of {c}. "
        f"What is the total score? (Think: {a} × {b} + {c}.)"
    )
    return MathSpec(
        subject="Math",
        topic="order of operations",
        difficulty_level=difficulty,
        question_text=text,
        scaffolding_hints=[_GENERIC_START, "Multiply the points from levels, then add the bonus."],
        expected_answer=str(ans),
        signature=f"pemdas:{a}*{b}+{c}",
    )


def _one_step_equations_specs(rng: random.Random, difficulty: DifficultyLevel) -> MathSpec:
    if difficulty == "simplified":
        x = rng.randint(3, 12)
        a = rng.randint(2, 9)
        # x + a = b
        b = x + a
        text = f"Solve for n: n + {a} = {b}. What is n?"
        return MathSpec(
            subject="Math",
            topic="one-step equations",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Undo the addition — subtract the same number from both sides."],
            expected_answer=str(x),
            signature=f"eq+:n+{a}={b}",
        )

    if difficulty == "increased":
        x = rng.randint(2, 15)
        a = rng.choice([2, 3, 4, 5, 6])
        b = a * x
        text = (
            f"Tickets cost ${a} each. You spend ${b} in all. "
            f"How many tickets did you buy? (Solve: {a}n = {b}.)"
        )
        return MathSpec(
            subject="Math",
            topic="one-step equations",
            difficulty_level=difficulty,
            question_text=text,
            scaffolding_hints=[_GENERIC_START, "Divide both sides by the ticket price."],
            expected_answer=str(x),
            signature=f"eq*:{a}n={b}",
        )

    x = rng.randint(4, 20)
    a = rng.randint(3, 12)
    b = x + a
    name = rng.choice(["Leo", "Nina", "Chris", "Pat"])
    text = (
        f"{name} had some cards, bought {a} more, and then had {b}. "
        f"How many cards did {name} start with?"
    )
    return MathSpec(
        subject="Math",
        topic="one-step equations",
        difficulty_level=difficulty,
        question_text=text,
        scaffolding_hints=[_GENERIC_START, "Work backwards from the ending amount."],
        expected_answer=str(x),
        signature=f"eqstory:{b}-{a}",
    )


_TOPIC_BUILDERS: dict[str, Callable[[random.Random, DifficultyLevel], MathSpec]] = {
    "unit price": _unit_price_specs,
    "arithmetic word problems": _arithmetic_word_specs,
    "fractions": _fractions_specs,
    "percentages": _percentages_specs,
    "order of operations": _order_of_operations_specs,
    "one-step equations": _one_step_equations_specs,
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

    for index in range(count * 10):
        if len(questions) >= count:
            break
        spec = builder(_rng(student_id, date_str, topic, index), difficulty)
        sig_hash = param_signature_hash(topic, spec.signature)
        if sig_hash in used:
            continue
        used.add(sig_hash)
        # Keep at most one soft hint after the generic opener for the UI.
        hints = list(spec.scaffolding_hints[:2])
        questions.append(
            GeneratedQuestion(
                subject=spec.subject,
                topic=topic,
                difficulty_level=spec.difficulty_level,
                question_text=spec.question_text,
                scaffolding_hints=hints,
                expected_answer=spec.expected_answer,
            )
        )
    return questions


def collect_used_math_signatures(
    recent_texts: Sequence[str],
    topics: Sequence[str],
) -> Set[str]:
    used: Set[str] = set()
    for topic in topics:
        for text in recent_texts:
            used.add(param_signature_hash(topic, text))
    return used
