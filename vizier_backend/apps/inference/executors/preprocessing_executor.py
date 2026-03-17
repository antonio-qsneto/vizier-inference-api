"""Preprocessing helper for inference inputs before GPU execution."""

from __future__ import annotations

import os
from pathlib import Path

from services.dicom_pipeline import DicomZipToNpzService


def _is_nifti_file(path: str) -> bool:
    lower = str(path).lower()
    return lower.endswith(".nii") or lower.endswith(".nii.gz")


def _normalize_nifti_to_gzip(input_nifti_path: str, output_nifti_path: str) -> None:
    import nibabel as nib

    image = nib.load(input_nifti_path)
    nib.save(image, output_nifti_path)


class InferencePreprocessor:
    """Converts incoming upload types into normalized artifacts for inference."""

    def __init__(self):
        self.converter = DicomZipToNpzService()

    def prepare_input(
        self,
        *,
        input_file_path: str,
        work_dir: str,
        text_prompts: dict | None = None,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> dict[str, str]:
        text_prompts = text_prompts or {}
        Path(work_dir).mkdir(parents=True, exist_ok=True)

        input_path = str(input_file_path)
        normalized_npz_path = os.path.join(work_dir, "input.npz")
        original_nifti_path = os.path.join(work_dir, "original_image.nii.gz")

        lower = input_path.lower()
        if lower.endswith(".zip"):
            normalized_npz_path = self.converter.convert_zip_to_npz(
                zip_path=input_path,
                text_prompts=text_prompts,
                output_npz_path=normalized_npz_path,
                output_original_nifti_path=original_nifti_path,
                exam_modality=exam_modality,
                category_hint=category_hint,
            )
        elif lower.endswith(".npz"):
            self.converter.preprocess_existing_npz(
                npz_path=input_path,
                output_npz_path=normalized_npz_path,
                exam_modality=exam_modality,
                category_hint=category_hint,
                text_prompts=text_prompts,
            )
            self.converter.convert_npz_to_nifti(
                npz_path=normalized_npz_path,
                output_nifti_path=original_nifti_path,
            )
        elif _is_nifti_file(input_path):
            _normalize_nifti_to_gzip(input_path, original_nifti_path)
            self.converter.convert_nifti_to_npz(
                nifti_path=input_path,
                text_prompts=text_prompts,
                output_npz_path=normalized_npz_path,
                exam_modality=exam_modality,
                category_hint=category_hint,
            )
        else:
            raise ValueError("Unsupported input extension. Expected .zip, .npz, .nii, or .nii.gz")

        return {
            "normalized_input_npz": normalized_npz_path,
            "original_nifti": original_nifti_path,
        }
