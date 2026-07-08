#!/usr/bin/env python3
"""Daily cron entrypoint — generate adaptive worksheets for today."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.generator import generate_and_store_daily_worksheet  # noqa: E402


def main() -> int:
    result = generate_and_store_daily_worksheet()
    print(
        f"Generated {result.inserted_count} question(s) for {result.student_id} "
        f"on {result.question_date.isoformat()}"
    )
    for tp in result.topic_progress:
        print(f"  - {tp.subject}/{tp.topic}: {tp.success_rate}% → {tp.recommended_difficulty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
