from __future__ import annotations

from typing import Dict, List

from app.models import DifficultyLevel, TopicProgress

# Struggling topics get more practice; strong topics get fewer, harder items.
DIFFICULTY_WEIGHT: Dict[DifficultyLevel, float] = {
    "simplified": 1.4,
    "maintained": 1.0,
    "increased": 0.75,
}


def compute_topic_question_counts(
    topic_progress: List[TopicProgress],
    target_per_subject: int,
    *,
    adaptive: bool = True,
) -> Dict[str, int]:
    """
    Split target questions across topics within each subject.

    When adaptive=True, weight by recommended difficulty so struggling topics
    receive more practice items while strong topics receive fewer.
    """
    by_subject: Dict[str, List[TopicProgress]] = {}
    for tp in topic_progress:
        by_subject.setdefault(tp.subject, []).append(tp)

    counts: Dict[str, int] = {}
    for topics in by_subject.values():
        n = len(topics)
        if n == 0:
            continue
        if not adaptive or n == 1:
            base = max(1, target_per_subject // n)
            extra = target_per_subject % n
            for i, tp in enumerate(topics):
                key = f"{tp.subject}::{tp.topic}"
                counts[key] = base + (1 if i < extra else 0)
            continue

        weights = [DIFFICULTY_WEIGHT.get(tp.recommended_difficulty, 1.0) for tp in topics]
        total_weight = sum(weights) or float(n)
        raw = [(w / total_weight) * target_per_subject for w in weights]
        # Guarantee at least 1 question per topic, then distribute remainder by largest remainder.
        floored = [max(1, int(v)) for v in raw]
        assigned = sum(floored)
        # If we overshot (many topics), shrink largest first while keeping >=1.
        while assigned > target_per_subject and any(c > 1 for c in floored):
            idx = max(range(n), key=lambda i: floored[i])
            if floored[idx] > 1:
                floored[idx] -= 1
                assigned -= 1
            else:
                break
        # Distribute leftover to topics with largest fractional remainders.
        remainder = target_per_subject - assigned
        order = sorted(
            range(n),
            key=lambda i: (raw[i] - int(raw[i]), weights[i]),
            reverse=True,
        )
        for i in order:
            if remainder <= 0:
                break
            floored[i] += 1
            remainder -= 1
        for i, tp in enumerate(topics):
            key = f"{tp.subject}::{tp.topic}"
            counts[key] = floored[i]
    return counts
