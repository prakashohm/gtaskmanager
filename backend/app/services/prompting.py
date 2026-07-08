from __future__ import annotations

from typing import Dict, List

from app.models import TopicProgress

IEP_ACCOMMODATIONS = """
IEP ACCOMMODATIONS (MANDATORY — never violate):
- Use simple sentence structures (one idea per sentence).
- Use highly literal, concrete language. Avoid figurative speech unless you immediately explain it.
- No trick questions, no hidden assumptions, no multi-step traps.
- Reading passages must be short and at an accessible Lexile when difficulty is simplified.
- Math questions must state exactly what to find; provide formulas in scaffolding when simplified.
- Word problems must use familiar contexts and round numbers when possible.
""".strip()

DIFFICULTY_GUIDANCE = {
    "simplified": """
Difficulty: SIMPLIFIED (recent success < 60%).
- Shorter problems with fewer steps.
- Include explicit scaffolding: formulas, sentence starters, worked mini-examples in scaffolding_hints.
- Reading: very short passage (3–5 sentences), literal comprehension only.
""".strip(),
    "maintained": """
Difficulty: MAINTAINED (recent success 60%–80%).
- Match current grade-appropriate level without adding extra complexity.
- Moderate scaffolding only when the skill typically needs it.
""".strip(),
    "increased": """
Difficulty: INCREASED (recent success > 80%).
- Slightly harder: one extra step, modest distractors, or a passage ~1 Lexile band higher.
- Still follow all IEP accommodations — never use trick questions.
""".strip(),
}


def build_system_prompt() -> str:
    return (
        "You are an expert special-education worksheet author. "
        "You create daily practice questions for a student with an IEP. "
        "You MUST respond with valid JSON only — no markdown fences, no commentary."
    )


def build_user_prompt(
    student_id: str,
    question_date: str,
    topic_progress: List[TopicProgress],
    topic_question_counts: Dict[str, int],
) -> str:
    lines = [
        f"Generate adaptive daily worksheet questions for student '{student_id}' on {question_date}.",
        IEP_ACCOMMODATIONS,
        "",
        "Pacing: each question should take about 2–3 minutes (substantive, not trivial).",
        "Reading questions may include a short passage; math questions may include a brief word problem.",
        "",
        "Topics and adaptive targets:",
    ]
    for tp in topic_progress:
        key = f"{tp.subject}::{tp.topic}"
        count = topic_question_counts.get(key, 5)
        lines.append(
            f"- {tp.subject} / {tp.topic}: recent success {tp.success_rate}% "
            f"({tp.correct}/{tp.attempts} in lookback) → {tp.recommended_difficulty}"
        )
        lines.append(DIFFICULTY_GUIDANCE[tp.recommended_difficulty])
        lines.append(f"  Create exactly {count} question(s) for this topic.")
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
            '      "scaffolding_hints": ["string", "..."],',
            '      "expected_answer": "string"',
            "    }",
            "  ]",
            "}",
            "",
            "Use the recommended difficulty per topic. expected_answer must be concise and literal.",
        ]
    )
    return "\n".join(lines)
