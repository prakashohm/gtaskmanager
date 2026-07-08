from __future__ import annotations

from typing import Dict, List

from app.models import TopicProgress


def compute_topic_question_counts(
    topic_progress: List[TopicProgress],
    target_per_subject: int,
) -> Dict[str, int]:
    """Split target questions evenly across topics within each subject."""
    by_subject: Dict[str, List[TopicProgress]] = {}
    for tp in topic_progress:
        by_subject.setdefault(tp.subject, []).append(tp)

    counts: Dict[str, int] = {}
    for topics in by_subject.values():
        n = len(topics)
        base = max(1, target_per_subject // n)
        extra = target_per_subject % n
        for i, tp in enumerate(topics):
            key = f"{tp.subject}::{tp.topic}"
            counts[key] = base + (1 if i < extra else 0)
    return counts
