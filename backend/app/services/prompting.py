from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from app.models import TopicProgress

TONE_GUIDANCE = """
TONE (mandatory):
- Guhan is a 9th grader who struggles with basic math — write for a teenager, not a
  young child. No "3 apples" or "Timmy has 5 candies" framing.
- Use real, teen-relatable contexts: money (prices, discounts, allowance, phone
  data plans), sports stats, distances/travel time, cooking/recipe scaling,
  video game currency, part-time job hours/pay.
- Plain, direct language. No trick questions, no hidden assumptions, no multi-step
  traps buried in the wording — the challenge should be the math, not decoding the prompt.
- State exactly what to find at the end of the problem.
""".strip()

DIFFICULTY_GUIDANCE = {
    "simplified": """
Difficulty: SIMPLIFIED (recent success < 60%).
- Small, clean numbers. One operation, or two at most.
- Keep the wording short — one context sentence, then the question.
""".strip(),
    "maintained": """
Difficulty: MAINTAINED (recent success 60%-80%).
- Grade-appropriate numbers (can include decimals/fractions/negatives where the topic calls for it).
- Two steps is fine if the topic naturally needs it (e.g. percent-of-a-number then compare).
""".strip(),
    "increased": """
Difficulty: INCREASED (recent success > 80%).
- One extra step or a slightly less obvious setup (e.g. percent increase THEN a follow-up
  comparison, or an equation with a term on both sides).
- Still one clean topic — don't blend in an unrelated skill just to add difficulty.
""".strip(),
}

# Shown to the LLM as a description of what "same pattern" means for each topic, so
# repeated problems within a cluster share the underlying skill instead of just
# sharing a subject label.
PATTERN_GUIDANCE = {
    "arithmetic word problems": "Same operation type per cluster (e.g. all multi-step addition/subtraction, or all multiplication/division) with a decimal or whole-number twist.",
    "fractions": "Same fraction operation per cluster (e.g. all adding unlike fractions, or all multiplying a fraction by a whole number).",
    "percentages": "Same percent skill per cluster (e.g. all 'find the discount price', or all 'percent increase/decrease').",
    "unit price": "Same unit-rate setup per cluster (cost per item / cost per unit), varying the item and numbers.",
    "order of operations": "Same operation mix per cluster (e.g. all parentheses + multiplication, or all exponents + addition), varying the numbers.",
    "one-step equations": "Same equation shape per cluster (e.g. all 'x + a = b', or all 'a * x = b'), varying the numbers and context.",
}


def build_system_prompt() -> str:
    return (
        "You are an expert math curriculum writer creating daily practice word "
        "problems for a 9th-grade student building basic math fluency. "
        "You MUST respond with valid JSON only — no markdown fences, no commentary."
    )


def build_user_prompt(
    student_id: str,
    question_date: str,
    topic_progress: List[TopicProgress],
    topic_question_counts: Dict[str, int],
    *,
    avoid_questions: Optional[Sequence[str]] = None,
    variety_seed: Optional[str] = None,
) -> str:
    lines = [
        f"Generate today's math practice worksheet for student '{student_id}' on {question_date}.",
        TONE_GUIDANCE,
        "",
        "Pacing: each problem should take a few minutes to work through with hints — "
        "substantive, not a one-liner.",
        "",
        "Topics for today (each is a CLUSTER of same-pattern problems — see below):",
    ]
    for tp in topic_progress:
        key = f"{tp.subject}::{tp.topic}"
        count = topic_question_counts.get(key, 3)
        pattern = PATTERN_GUIDANCE.get(tp.topic.strip().lower(), "")
        lines.append(
            f"- {tp.subject} / {tp.topic}: recent success {tp.success_rate}% "
            f"({tp.correct}/{tp.attempts} in lookback) -> {tp.recommended_difficulty}"
        )
        lines.append(DIFFICULTY_GUIDANCE[tp.recommended_difficulty])
        lines.append(f"  Create exactly {count} problem(s) for this topic, ALL at the SAME difficulty band above.")
        if pattern:
            lines.append(
                f"  Reinforcement pattern for this cluster: {pattern} "
                "Vary the numbers/context between problems in the cluster, but keep the "
                "underlying skill identical so solving one helps with the next."
            )
        lines.append("")

    if variety_seed:
        lines.append(f"Variety seed (use to pick fresh contexts/numbers): {variety_seed}")
        lines.append("")

    avoid = [t.strip() for t in (avoid_questions or []) if t and t.strip()]
    if avoid:
        lines.append(
            "ANTI-REPEAT (mandatory): Do NOT repeat, closely paraphrase, or reuse the same "
            "numbers/context as any of these recent problems. Invent new contexts and values."
        )
        # Cap prompt size — keep the most recent / first N texts.
        for text in avoid[:40]:
            clipped = text if len(text) <= 220 else text[:217] + "..."
            lines.append(f'- "{clipped}"')
        lines.append("")

    lines.extend(
        [
            "Return JSON matching this schema:",
            "{",
            '  "student_id": "string",',
            '  "question_date": "YYYY-MM-DD",',
            '  "questions": [',
            "    {",
            '      "subject": "string",',
            '      "topic": "string",',
            '      "difficulty_level": "simplified" | "maintained" | "increased",',
            '      "question_text": "string",',
            '      "scaffolding_hints": ["string"],',
            '      "expected_answer": "string"',
            "    }",
            "  ]",
            "}",
            "",
            "expected_answer must be concise and exact (a number, or a short phrase like '3/4' or '$12.50').",
            "scaffolding_hints must contain EXACTLY ONE short 'getting started' nudge — a pointer "
            "toward the right approach or formula, NOT a worked solution and NOT the final answer. "
            "For example 'Percent means per 100 — think about what fraction of the price that is' "
            "is fine; walking through the arithmetic or stating the result is not.",
            "Every question_text must be unique and different from the anti-repeat list.",
        ]
    )
    return "\n".join(lines)
