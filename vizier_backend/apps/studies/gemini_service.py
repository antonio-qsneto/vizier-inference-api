"""
Gemini integration for descriptive medical analysis in study results.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

try:
    from google import genai
except Exception:  # pragma: no cover - dependency fallback for partial envs
    genai = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-lite"


def _normalize_segments_for_prompt(
    segments_legend: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not segments_legend:
        return []

    normalized: list[dict[str, Any]] = []
    for item in segments_legend:
        raw_id = item.get("id", 0)
        try:
            segment_id = int(raw_id)
        except Exception:
            segment_id = 0

        label = str(item.get("label") or "").strip() or f"Label {segment_id}"
        percentage = item.get("percentage")
        try:
            percentage = round(float(percentage), 4)
        except Exception:
            percentage = 0.0

        normalized.append(
            {
                "id": segment_id,
                "label": label,
                "percentage": percentage,
                "voxels": int(item.get("voxels", 0)),
            }
        )

    return normalized


def build_descriptive_prompt(study: Any, segments_legend: list[dict[str, Any]] | None) -> str:
    modality = str(getattr(study, "exam_modality", "") or "nao informada").strip()
    category = str(getattr(study, "category", "") or "nao informada").strip()
    segments = _normalize_segments_for_prompt(segments_legend)
    segments_json = json.dumps(segments, ensure_ascii=False)

    return (
        "Você é um assistente de apoio radiológico. Com base nos metadados e segmentos abaixo, "
        "escreva 2-3 frases em português descrevendo os achados mais relevantes "
        "(inclua percentuais aproximados), sem fechar diagnóstico definitivo. "
        "Termine com uma ressalva breve de apoio à decisão clínica. "
        f"Dados: modalidade={modality}, categoria={category}, segmentos={segments_json}."
    )


def _extract_google_error_details(exc: Exception) -> tuple[int | None, str | None, str]:
    message = str(exc)
    status_code: int | None = None
    status_name: str | None = None

    if hasattr(exc, "args") and exc.args and isinstance(exc.args[0], dict):
        details = exc.args[0].get("error", {})
        if isinstance(details, dict):
            raw_code = details.get("code")
            try:
                status_code = int(raw_code) if raw_code is not None else None
            except Exception:
                status_code = None
            status_name = details.get("status")
            message = str(details.get("message") or message)

    return status_code, status_name, message


def call_gemini(prompt: str) -> str | None:
    api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        logger.warning("[Gemini] GOOGLE_API_KEY not configured")
        return None

    if genai is None:
        logger.warning("[Gemini] google-genai dependency not installed")
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = str(getattr(response, "text", "") or "").strip()
        return text or None
    except Exception as exc:
        status_code, status_name, message = _extract_google_error_details(exc)
        if status_code == 503 or str(status_name or "").upper() == "UNAVAILABLE":
            logger.warning("[Gemini] Service overloaded: %s", message)
            return None

        logger.warning("[Gemini] API error: %s", message, exc_info=True)
        return None
