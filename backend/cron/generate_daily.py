#!/usr/bin/env python3
"""Daily cron entrypoint — generate adaptive worksheets for today (idempotent)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import GenerateWorksheetRequest  # noqa: E402
from app.services.generator import generate_and_store_daily_worksheet  # noqa: E402


def main() -> int:
    # skip_if_exists=True (default): do not append a second sheet if UI already generated.
    result = generate_and_store_daily_worksheet(
        GenerateWorksheetRequest(replace_existing=False, skip_if_exists=True)
    )
    if result.skipped_existing and result.inserted_count == 0:
        print(
            f"Skipped — worksheet already exists for {result.student_id} "
            f"on {result.question_date.isoformat()} ({len(result.questions)} question(s))"
        )
    else:
        print(
            f"Generated {result.inserted_count} question(s) for {result.student_id} "
            f"on {result.question_date.isoformat()}"
            + (" (filled missing subjects)" if result.skipped_existing else "")
        )
    for tp in result.topic_progress:
        print(f"  - {tp.subject}/{tp.topic}: {tp.success_rate}% → {tp.recommended_difficulty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
