"""Prompt catalog helpers for async inference jobs."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings
import logging


logger = logging.getLogger(__name__)


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower()


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any]:
    catalog_path = Path(settings.BASE_DIR) / "data" / "categories.json"
    with open(catalog_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return payload
    return {}


def _resolve_modality_node(catalog: dict[str, Any], exam_modality: str) -> dict[str, Any]:
    wanted = _normalize(exam_modality)
    if not wanted:
        return {}

    for key, value in catalog.items():
        if _normalize(key) == wanted and isinstance(value, dict):
            return value
    return {}


def _extract_prompt_text(item: Any, *, category_id: str) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        prompt = str(item.get("prompt") or item.get("name") or item.get("label") or "").strip()
        if prompt:
            return prompt
    fallback = str(category_id or "").strip()
    if fallback:
        return f"segmentation of {fallback}"
    return ""


def _resolve_targets(modality_node: dict[str, Any], category_id: str) -> list[Any]:
    wanted = _normalize(category_id)
    if not wanted:
        return []

    # Common/simple structure: {"MRI": {"head": ["tumor", ...]}}
    for key, value in modality_node.items():
        if _normalize(key) == wanted:
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested_targets = value.get("targets")
                if isinstance(nested_targets, list):
                    return nested_targets
            return []

    # Optional richer structure: {"groups":[{"id":"head","targets":[...]}]}
    for group_key in ("groups", "categories", "regions"):
        groups = modality_node.get(group_key)
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            aliases = [
                group.get("id"),
                group.get("slug"),
                group.get("key"),
                group.get("name"),
                group.get("title"),
            ]
            if any(_normalize(alias) == wanted for alias in aliases):
                targets = group.get("targets") or group.get("items") or []
                if isinstance(targets, list):
                    return targets
                return []

    return []


def build_text_prompts_for_job(
    *,
    exam_modality: str | None,
    category_id: str | None,
) -> dict[str, Any]:
    """
    Build BiomedParse text prompts for async worker jobs.

    Returns:
        Dict like {"1": "...", "2": "...", "instance_label": 0}.
        Always returns at least one prompt plus instance_label.
    """
    modality_text = str(exam_modality or "").strip()
    category_text = str(category_id or "").strip()
    if not modality_text and not category_text:
        return {
            "1": "lesion",
            "instance_label": 0,
        }

    try:
        catalog = _load_catalog()
    except Exception:
        logger.warning("Failed to load categories catalog for async prompt generation", exc_info=True)
        catalog = {}
    modality_node = _resolve_modality_node(catalog, modality_text)
    targets = _resolve_targets(modality_node, category_text) if modality_node else []

    prompts: dict[str, Any] = {}
    prompt_index = 1
    for target in targets:
        prompt_text = _extract_prompt_text(target, category_id=category_text)
        if not prompt_text:
            continue
        prompts[str(prompt_index)] = prompt_text
        prompt_index += 1

    # Safety fallback: never run with empty prompts.
    if prompt_index == 1:
        if category_text:
            prompts["1"] = f"segmentation of {category_text}"
        elif modality_text:
            prompts["1"] = f"lesion in {modality_text}"
        else:
            prompts["1"] = "lesion"

    prompts["instance_label"] = 0
    return prompts
