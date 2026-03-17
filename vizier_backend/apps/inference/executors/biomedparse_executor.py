"""BiomedParse execution adapter used by async worker pipeline."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from django.conf import settings

from apps.inference.client import InferenceClient
from services.dicom_pipeline import DicomZipToNpzService
from services.nifti_converter import NiftiConverter


def _is_nifti_file(path: str) -> bool:
    lower = str(path).lower()
    return lower.endswith(".nii") or lower.endswith(".nii.gz")


def _normalize_nifti_to_gzip(input_nifti_path: str, output_nifti_path: str) -> None:
    import nibabel as nib

    image = nib.load(input_nifti_path)
    nib.save(image, output_nifti_path)


class BiomedParseExecutor:
    """Executes the model workflow and returns generated artifact paths."""

    def __init__(self):
        self.client = InferenceClient()
        self.timeout_seconds = int(getattr(settings, "INFERENCE_API_TIMEOUT", 300))
        self.poll_interval_seconds = int(getattr(settings, "INFERENCE_POLL_INTERVAL", 5))

    def run(
        self,
        *,
        input_file_path: str,
        work_dir: str,
        text_prompts: dict | None = None,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> dict[str, str]:
        """Run full pipeline and return local output paths."""
        text_prompts = text_prompts or {}
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        input_path = str(input_file_path)
        normalized_npz_path = os.path.join(work_dir, "input.npz")
        original_nifti_path = os.path.join(work_dir, "original_image.nii.gz")
        mask_npz_path = os.path.join(work_dir, "mask.npz")
        mask_nifti_path = os.path.join(work_dir, "mask.nii.gz")
        summary_path = os.path.join(work_dir, "summary.json")

        converter = DicomZipToNpzService()

        lower = input_path.lower()
        if lower.endswith(".zip"):
            normalized_npz_path = converter.convert_zip_to_npz(
                zip_path=input_path,
                text_prompts=text_prompts,
                output_npz_path=normalized_npz_path,
                output_original_nifti_path=original_nifti_path,
                exam_modality=exam_modality,
                category_hint=category_hint,
            )
        elif lower.endswith(".npz"):
            converter.preprocess_existing_npz(
                npz_path=input_path,
                output_npz_path=normalized_npz_path,
                exam_modality=exam_modality,
                category_hint=category_hint,
                text_prompts=text_prompts,
            )
            converter.convert_npz_to_nifti(
                npz_path=normalized_npz_path,
                output_nifti_path=original_nifti_path,
            )
        elif _is_nifti_file(input_path):
            _normalize_nifti_to_gzip(input_path, original_nifti_path)
            converter.convert_nifti_to_npz(
                nifti_path=input_path,
                text_prompts=text_prompts,
                output_npz_path=normalized_npz_path,
                exam_modality=exam_modality,
                category_hint=category_hint,
            )
        else:
            raise ValueError("Unsupported input extension. Expected .zip, .npz, .nii, or .nii.gz")

        external_job_id = self.client.submit_job(normalized_npz_path)

        started = time.monotonic()
        last_status_payload = None
        while True:
            status_payload = self.client.get_status(external_job_id)
            last_status_payload = status_payload
            status_name = str(status_payload.get("status") or "").strip().lower()
            if status_name in {"completed", "succeeded"}:
                break
            if status_name in {"failed", "error"}:
                raise RuntimeError(f"Inference API failed job {external_job_id}: {status_payload}")
            if time.monotonic() - started > self.timeout_seconds:
                raise TimeoutError(f"Inference API timed out for job {external_job_id}")
            time.sleep(self.poll_interval_seconds)

        if not self.client.get_results(external_job_id, mask_npz_path):
            raise RuntimeError(f"Failed to download mask results for external job {external_job_id}")

        if not NiftiConverter.segs_npz_to_nifti(mask_npz_path, mask_nifti_path):
            raise RuntimeError("Failed to convert mask NPZ to NIfTI")

        summary_payload = {
            "executor": "biomedparse",
            "external_job_id": external_job_id,
            "input_file": os.path.basename(input_file_path),
            "normalized_npz_file": os.path.basename(normalized_npz_path),
            "original_nifti_file": os.path.basename(original_nifti_path),
            "mask_nifti_file": os.path.basename(mask_nifti_path),
            "status": "completed",
            "external_status": last_status_payload,
        }
        with open(summary_path, "w", encoding="utf-8") as handle:
            json.dump(summary_payload, handle, ensure_ascii=True, indent=2)

        return {
            "normalized_input_npz": normalized_npz_path,
            "original_nifti": original_nifti_path,
            "mask_nifti": mask_nifti_path,
            "summary_json": summary_path,
            "external_job_id": external_job_id,
        }
