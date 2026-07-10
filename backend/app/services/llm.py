from __future__ import annotations

import hashlib
import time
from typing import Dict, List, Optional, Sequence

from app.config import get_settings
from app.models import DailyWorksheetResponse, TopicProgress
from app.services.prompting import build_system_prompt, build_user_prompt

MAX_OUTPUT_TOKENS = 8000

# Gemini models to try in order, used only as a fallback when Claude is
# rate-limited, overloaded, out of credits, or unreachable.
GEMINI_MODEL_FALLBACKS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
)
GEMINI_RETRIES_PER_MODEL = 3
GEMINI_RETRY_BASE_SECONDS = 2.0


class ClaudeUnavailableError(RuntimeError):
    """Claude is rate-limited, overloaded, out of credits, unreachable, or
    unconfigured — the caller should retry via the Gemini fallback if one is
    configured. Not raised for content-shape problems (e.g. a refusal) or bad
    requests, which a fallback provider wouldn't meaningfully fix and which
    should stay visible rather than being silently masked."""


def _strip_json_fences(text: str) -> str:
    import re

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_llm_json(raw: str) -> DailyWorksheetResponse:
    import json

    payload = json.loads(_strip_json_fences(raw))
    return DailyWorksheetResponse.model_validate(payload)


def _effort_for_progress(topic_progress: List[TopicProgress]) -> str:
    """More effort (deeper reasoning about variety/constraints) when any topic is in the increased band."""
    if any(tp.recommended_difficulty == "increased" for tp in topic_progress):
        return "high"
    return "medium"


def _temperature_for_progress(topic_progress: List[TopicProgress]) -> float:
    """Slightly higher temperature when any topic is in the increased band.
    Gemini fallback only — Claude rejects non-default sampling parameters."""
    if any(tp.recommended_difficulty == "increased" for tp in topic_progress):
        return 0.55
    return 0.4


def _variety_seed(student_id: str, question_date: str, topics: Sequence[str]) -> str:
    material = f"{student_id}|{question_date}|{'|'.join(sorted(topics))}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def _worksheet_json_schema() -> dict:
    """JSON schema for DailyWorksheetResponse, shaped for Claude's structured outputs
    (output_config.format) so the response is guaranteed valid JSON matching this shape."""
    return {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "question_date": {"type": "string", "format": "date"},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string"},
                        "topic": {"type": "string"},
                        "difficulty_level": {
                            "type": "string",
                            "enum": ["simplified", "maintained", "increased"],
                        },
                        "question_text": {"type": "string"},
                        "scaffolding_hints": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "expected_answer": {"type": "string"},
                    },
                    "required": [
                        "subject",
                        "topic",
                        "difficulty_level",
                        "question_text",
                        "scaffolding_hints",
                        "expected_answer",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["student_id", "question_date", "questions"],
        "additionalProperties": False,
    }


def generate_worksheet_json(
    student_id: str,
    question_date: str,
    topic_progress: List[TopicProgress],
    topic_question_counts: Optional[Dict[str, int]] = None,
    *,
    avoid_questions: Optional[Sequence[str]] = None,
) -> DailyWorksheetResponse:
    from app.services.question_counts import compute_topic_question_counts

    settings = get_settings()
    if topic_question_counts is None:
        topic_question_counts = compute_topic_question_counts(
            topic_progress,
            settings.target_questions_per_subject,
            adaptive=settings.adaptive_question_counts,
        )
    system_prompt = build_system_prompt()
    variety_seed = _variety_seed(
        student_id, question_date, [f"{p.subject}::{p.topic}" for p in topic_progress]
    )
    user_prompt = build_user_prompt(
        student_id,
        question_date,
        topic_progress,
        topic_question_counts,
        avoid_questions=avoid_questions,
        variety_seed=variety_seed,
    )
    effort = _effort_for_progress(topic_progress)

    try:
        return _generate_claude(system_prompt, user_prompt, effort=effort)
    except ClaudeUnavailableError as claude_exc:
        if not settings.gemini_api_key:
            raise
        print(f"[worksheet-llm] Claude unavailable, falling back to Gemini: {claude_exc}")
        temperature = _temperature_for_progress(topic_progress)
        try:
            return _generate_gemini(system_prompt, user_prompt, temperature=temperature)
        except Exception as gemini_exc:
            raise RuntimeError(
                f"Claude is unavailable ({claude_exc}) and the Gemini fallback also "
                f"failed: {gemini_exc}"
            ) from gemini_exc


def _format_claude_failure(exc: Exception) -> str:
    error_type = getattr(exc, "type", None) or ""
    status_code = getattr(exc, "status_code", None)
    detail = str(exc)
    if error_type == "billing_error" or "credit balance" in detail.lower():
        return (
            "Claude account is out of credits. Add credits at "
            "https://console.anthropic.com/settings/billing. Details: " + detail
        )
    if error_type == "overloaded_error" or status_code == 529:
        return (
            "Claude is busy right now (high demand). Wait 30-60 seconds and tap "
            "Regenerate again. Details: " + detail
        )
    if error_type == "rate_limit_error" or status_code == 429:
        return "Claude rate limit reached. Wait a minute and retry. Details: " + detail
    if error_type == "authentication_error" or status_code == 401:
        return "Claude API key is invalid or missing. Check ANTHROPIC_API_KEY. Details: " + detail
    return "Claude request failed. Details: " + detail


def _is_claude_capacity_or_billing_issue(exc: Exception) -> bool:
    """True for failures worth retrying via the Gemini fallback: rate limits,
    overload, server errors, out-of-credits. False for things a fallback
    provider wouldn't fix and that should stay visible instead of being
    silently masked (bad request shape, invalid API key)."""
    status_code = getattr(exc, "status_code", None)
    error_type = getattr(exc, "type", None) or ""
    if status_code in (429, 500, 502, 503, 529):
        return True
    if error_type in ("rate_limit_error", "overloaded_error", "billing_error"):
        return True
    return "credit balance" in str(exc).lower()


def _generate_claude(
    system_prompt: str, user_prompt: str, *, effort: str = "medium"
) -> DailyWorksheetResponse:
    import anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ClaudeUnavailableError("ANTHROPIC_API_KEY is not set")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=system_prompt,
            # Claude Sonnet 5 runs adaptive thinking by default; this task is plain
            # structured content generation and runs many times a day (cron + parent
            # "Regenerate" button), so thinking is switched off for speed/cost.
            thinking={"type": "disabled"},
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": _worksheet_json_schema()},
            },
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIConnectionError as exc:
        raise ClaudeUnavailableError(f"Claude request failed: network error ({exc})") from exc
    except anthropic.APIStatusError as exc:
        message = _format_claude_failure(exc)
        if _is_claude_capacity_or_billing_issue(exc):
            raise ClaudeUnavailableError(message) from exc
        raise RuntimeError(message) from exc

    if response.stop_reason == "refusal":
        detail = ""
        if response.stop_details is not None:
            detail = f" ({response.stop_details.category})"
        raise RuntimeError(
            f"Claude declined to generate this worksheet{detail}. Try again or adjust the prompt."
        )

    text = next((block.text for block in response.content if block.type == "text"), None)
    if not text:
        raise RuntimeError("Claude returned no text content for the worksheet")
    return _parse_llm_json(text)


# --- Gemini: fallback provider only (not selectable as primary) ---


def _gemini_models_to_try(primary: str) -> List[str]:
    ordered = [primary] + [m for m in GEMINI_MODEL_FALLBACKS if m != primary]
    seen = set()
    result: List[str] = []
    for model in ordered:
        if model not in seen:
            seen.add(model)
            result.append(model)
    return result


def _gemini_error_status(exc: Exception) -> Optional[int]:
    for attr in ("status_code", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    text = str(exc).lower()
    for code in (503, 502, 500, 429, 404):
        if str(code) in text:
            return code
    if "not_found" in text or "not found" in text:
        return 404
    if "unavailable" in text or "high demand" in text:
        return 503
    if "quota" in text or "resource_exhausted" in text:
        return 429
    return None


def _should_skip_to_next_model(exc: Exception) -> bool:
    """Skip to next model on capacity limits or unavailable model names."""
    status = _gemini_error_status(exc)
    if status in (404, 429, 500, 502, 503):
        return True
    return _is_transient_gemini_error(exc)


def _is_transient_gemini_error(exc: Exception) -> bool:
    status = _gemini_error_status(exc)
    return status in (429, 500, 502, 503)


def _format_gemini_failure(errors: List[str]) -> str:
    if not errors:
        return (
            "Gemini fallback is also temporarily unavailable on all tried models. "
            "Wait a minute and try again."
        )
    detail = "; ".join(errors[:4])
    if any("503" in e or "UNAVAILABLE" in e for e in errors):
        return (
            "Gemini fallback is busy right now (high demand). Details: " + detail
        )
    if any("429" in e for e in errors):
        return "Gemini fallback rate limit reached. Details: " + detail
    return "Gemini fallback request failed on all models. Details: " + detail


def _generate_gemini(
    system_prompt: str, user_prompt: str, *, temperature: float = 0.4
) -> DailyWorksheetResponse:
    from google import genai
    from google.genai import types
    from google.genai.errors import ClientError, ServerError

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    client = genai.Client(api_key=settings.gemini_api_key)
    model_errors: List[str] = []
    last_error: Optional[Exception] = None

    for model in _gemini_models_to_try(settings.gemini_model):
        for attempt in range(GEMINI_RETRIES_PER_MODEL):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                        response_mime_type="application/json",
                    ),
                )
                raw = response.text or "{}"
                return _parse_llm_json(raw)
            except (ClientError, ServerError) as exc:
                last_error = exc
                if _should_skip_to_next_model(exc):
                    if _gemini_error_status(exc) != 404 and attempt < GEMINI_RETRIES_PER_MODEL - 1:
                        time.sleep(GEMINI_RETRY_BASE_SECONDS * (attempt + 1))
                        continue
                    model_errors.append(f"{model}: {exc}")
                    break
                raise RuntimeError(f"Gemini fallback error ({model}): {exc}") from exc
            except Exception as exc:
                last_error = exc
                if _should_skip_to_next_model(exc):
                    if _gemini_error_status(exc) != 404 and attempt < GEMINI_RETRIES_PER_MODEL - 1:
                        time.sleep(GEMINI_RETRY_BASE_SECONDS * (attempt + 1))
                        continue
                    model_errors.append(f"{model}: {exc}")
                    break
                raise RuntimeError(f"Gemini fallback request failed ({model}): {exc}") from exc

    raise RuntimeError(_format_gemini_failure(model_errors)) from last_error
