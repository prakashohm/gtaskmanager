from __future__ import annotations

import hashlib
import time
from typing import Dict, List, Optional, Sequence

from app.config import get_settings
from app.models import DailyWorksheetResponse, TopicProgress
from app.services.prompting import build_system_prompt, build_user_prompt

# Models verified for generateContent on the current Gemini API (v1beta).
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


def _temperature_for_progress(topic_progress: List[TopicProgress]) -> float:
    """Slightly higher temperature when any topic is in the increased band."""
    if any(tp.recommended_difficulty == "increased" for tp in topic_progress):
        return 0.55
    return 0.4


def _variety_seed(student_id: str, question_date: str, topics: Sequence[str]) -> str:
    material = f"{student_id}|{question_date}|{'|'.join(sorted(topics))}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


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
    temperature = _temperature_for_progress(topic_progress)

    if settings.llm_provider == "openai":
        return _generate_openai(system_prompt, user_prompt, temperature=temperature)
    return _generate_gemini(system_prompt, user_prompt, temperature=temperature)


def _generate_openai(
    system_prompt: str, user_prompt: str, *, temperature: float = 0.4
) -> DailyWorksheetResponse:
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        return _parse_llm_json(raw)
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc


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
            "Gemini is temporarily unavailable on all tried models. "
            "Wait a minute and try again."
        )
    detail = "; ".join(errors[:4])
    if any("503" in e or "UNAVAILABLE" in e for e in errors):
        return (
            "Gemini is busy right now (high demand). Wait 30–60 seconds and tap "
            "Regenerate again. Details: " + detail
        )
    if any("429" in e for e in errors):
        return (
            "Gemini rate limit reached. Wait a minute and retry, or set "
            "LLM_PROVIDER=openai with OPENAI_API_KEY. Details: " + detail
        )
    return "Gemini request failed on all models. Details: " + detail


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
                raise RuntimeError(f"Gemini error ({model}): {exc}") from exc
            except Exception as exc:
                last_error = exc
                if _should_skip_to_next_model(exc):
                    if _gemini_error_status(exc) != 404 and attempt < GEMINI_RETRIES_PER_MODEL - 1:
                        time.sleep(GEMINI_RETRY_BASE_SECONDS * (attempt + 1))
                        continue
                    model_errors.append(f"{model}: {exc}")
                    break
                raise RuntimeError(f"Gemini request failed ({model}): {exc}") from exc

    raise RuntimeError(_format_gemini_failure(model_errors)) from last_error
