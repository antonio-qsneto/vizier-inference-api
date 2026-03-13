"""S3 object key layout helpers for async inference artifacts."""

from __future__ import annotations

import os
import re
from pathlib import Path


def sanitize_filename(filename: str) -> str:
    """Return a filesystem-safe filename for object keys."""
    raw = Path(filename or "upload.bin").name
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-")
    return normalized or "upload.bin"


def _join(*parts: str) -> str:
    return "/".join(str(part).strip("/") for part in parts if str(part).strip("/"))


def raw_input_key(tenant_id: str, job_id: str, filename: str) -> str:
    return _join("raw", tenant_id, job_id, "input", sanitize_filename(filename))


def normalized_input_key(tenant_id: str, job_id: str) -> str:
    return _join("normalized", tenant_id, job_id, "input.npz")


def output_original_nifti_key(tenant_id: str, job_id: str) -> str:
    return _join("output", tenant_id, job_id, "original_image.nii.gz")


def output_mask_nifti_key(tenant_id: str, job_id: str) -> str:
    return _join("output", tenant_id, job_id, "mask.nii.gz")


def output_mask_npz_key(tenant_id: str, job_id: str) -> str:
    return _join("output", tenant_id, job_id, "mask.npz")


def output_summary_key(tenant_id: str, job_id: str) -> str:
    return _join("output", tenant_id, job_id, "summary.json")


def audit_processing_metadata_key(tenant_id: str, job_id: str) -> str:
    return _join("audit", tenant_id, job_id, "processing-metadata.json")


def infer_upload_type_from_key(key: str) -> str:
    lower = os.path.basename(key).lower()
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".npz"):
        return "npz"
    if lower.endswith(".nii") or lower.endswith(".nii.gz"):
        return "nifti"
    return "binary"
