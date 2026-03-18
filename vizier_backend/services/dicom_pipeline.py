"""
Medical volume to NPZ conversion pipeline.
Handles ZIP extraction, DICOM loading, NIfTI/NPZ fallbacks, preprocessing, and NPZ creation.
"""

import os
import shutil
import tempfile
import zipfile
import math
import numpy as np
import pydicom
import nibabel as nib
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class DicomZipToNpzService:
    """Service for converting ZIP/NIfTI/NPZ inputs to a BiomedParse v2-compatible NPZ."""
    
    def __init__(self):
        # Legacy spatial knobs are kept for backwards compatibility in settings,
        # but the inference preprocessing path preserves original shape so the
        # model can apply its own process_input(..., 512) resize internally.
        self.target_hw = settings.DICOM_TARGET_HW
        self.target_slices = settings.DICOM_TARGET_SLICES
        raw_keep_original_slices = getattr(settings, 'DICOM_KEEP_ORIGINAL_SLICES', True)
        if isinstance(raw_keep_original_slices, str):
            self.keep_original_slices = raw_keep_original_slices.strip().lower() in {'1', 'true', 'yes', 'on'}
        else:
            self.keep_original_slices = bool(raw_keep_original_slices)
        self.ct_windows = {
            'soft_tissues': {'width': 400.0, 'level': 40.0},
            'lung': {'width': 1500.0, 'level': -160.0},
            'brain': {'width': 80.0, 'level': 40.0},
            'bone': {'width': 1800.0, 'level': 400.0},
        }
        self.last_ingestion_report: dict = {}

    def _set_ingestion_report(self, report: dict | None) -> None:
        self.last_ingestion_report = dict(report or {})
    
    def convert_zip_to_npz(
        self,
        zip_path: str,
        text_prompts: dict | None = None,
        output_npz_path: str | None = None,
        output_original_nifti_path: str | None = None,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> str:
        """
        Convert a ZIP file into a single NPZ file.

        This method is intentionally side-effect light: it extracts into a
        subfolder next to the ZIP path so the caller can cleanup the parent
        temp directory (common in DRF upload flows).

        Args:
            zip_path: Path to the input ZIP file (DICOM folder layout, NIfTI, or NPZ).
            text_prompts: Dict with prompts for inference (stored into NPZ).
            output_npz_path: Optional explicit output path for the generated NPZ.

        Returns:
            Path to the generated NPZ file.

        Raises:
            ValueError: If processing fails.
        """
        if text_prompts is None:
            text_prompts = {}
        self._set_ingestion_report(None)

        work_dir = os.path.dirname(zip_path)
        extract_path = os.path.join(work_dir, 'extracted')

        try:
            logger.info("Processing ZIP input: %s", zip_path)

            # Ensure a clean extraction directory (caller usually controls work_dir)
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path, ignore_errors=True)
            os.makedirs(extract_path, exist_ok=True)

            # Unzip
            self._unzip(zip_path, extract_path)

            # First try DICOM canonical layout (legacy behavior).
            try:
                study_path = self._get_study_folder(extract_path)
                series_folders = self._get_series_folders(study_path)
                if not series_folders:
                    raise ValueError("No series folders found")

                selected_probe = self._select_best_series_probe_from_folders(series_folders)
                series_path = str(selected_probe['path'])
                logger.info("Using DICOM series folder: %s", os.path.basename(series_path))

                volume, spacing = self._load_series(series_path)
                logger.info("Loaded DICOM volume shape: %s", volume.shape)

                if output_original_nifti_path:
                    self._save_volume_as_nifti(
                        volume=volume,
                        output_nifti_path=output_original_nifti_path,
                        spacing_zyx=spacing,
                    )

                volume = self._preprocess(
                    volume=volume,
                    exam_modality=exam_modality,
                    category_hint=category_hint,
                )
                logger.info("Preprocessed DICOM volume shape: %s", volume.shape)

                npz_path = output_npz_path or os.path.join(work_dir, 'file.npz')
                self._save_npz(npz_path, volume, spacing, text_prompts)
                logger.info("Saved NPZ from DICOM ZIP: %s", npz_path)
                self._set_ingestion_report(
                    {
                        'source': 'dicom_canonical_layout',
                        'layout': 'canonical',
                        'selected_series_label': selected_probe.get('label'),
                        'selected_series_uid': selected_probe.get('series_uid'),
                        'candidate_series_count': selected_probe.get('candidate_count'),
                        'effective_slices': selected_probe.get('effective_slices'),
                        'matrix': [selected_probe.get('rows'), selected_probe.get('cols')],
                        'slice_spacing': selected_probe.get('slice_spacing'),
                    }
                )
                return npz_path
            except Exception as dicom_layout_error:
                # Some clients upload DICOM ZIPs without the canonical `DICOM/<study>/<series>`
                # structure. Try recursive series discovery before NIfTI/NPZ fallbacks.
                logger.info(
                    "ZIP does not match canonical DICOM layout (%s). Attempting DICOM discovery fallback.",
                    dicom_layout_error,
                )

            discovered_probes = self._discover_dicom_series_probes(extract_path)
            if discovered_probes:
                selected_probe = self._select_best_series_probe(discovered_probes)
                selected_files = selected_probe.get('files') or []
                volume, spacing = self._load_series_from_files(
                    selected_files,
                    source_label=selected_probe.get('label') or 'discovered-series',
                )
                logger.info(
                    "Loaded discovered DICOM volume shape: %s (series=%s)",
                    volume.shape,
                    selected_probe.get('label'),
                )

                if output_original_nifti_path:
                    self._save_volume_as_nifti(
                        volume=volume,
                        output_nifti_path=output_original_nifti_path,
                        spacing_zyx=spacing,
                    )

                volume = self._preprocess(
                    volume=volume,
                    exam_modality=exam_modality,
                    category_hint=category_hint,
                )
                npz_path = output_npz_path or os.path.join(work_dir, 'file.npz')
                self._save_npz(npz_path, volume, spacing, text_prompts)
                logger.info("Saved NPZ from discovered DICOM ZIP: %s", npz_path)
                self._set_ingestion_report(
                    {
                        'source': 'dicom_discovered_layout',
                        'layout': 'discovered',
                        'selected_series_label': selected_probe.get('label'),
                        'selected_series_uid': selected_probe.get('series_uid'),
                        'candidate_series_count': selected_probe.get('candidate_count'),
                        'effective_slices': selected_probe.get('effective_slices'),
                        'matrix': [selected_probe.get('rows'), selected_probe.get('cols')],
                        'slice_spacing': selected_probe.get('slice_spacing'),
                    }
                )
                return npz_path

            nifti_inside_zip = self._find_first_file(
                extract_path,
                [".nii.gz", ".nii"],
            )
            if nifti_inside_zip:
                logger.info("Detected NIfTI in ZIP: %s", nifti_inside_zip)
                if output_original_nifti_path:
                    self._normalize_nifti_to_gzip_file(
                        input_nifti_path=nifti_inside_zip,
                        output_nifti_path=output_original_nifti_path,
                    )
                npz_path = output_npz_path or os.path.join(work_dir, 'file.npz')
                return self.convert_nifti_to_npz(
                    nifti_path=nifti_inside_zip,
                    text_prompts=text_prompts,
                    output_npz_path=npz_path,
                    exam_modality=exam_modality,
                    category_hint=category_hint,
                )

            npz_inside_zip = self._find_first_file(extract_path, [".npz"])
            if npz_inside_zip:
                logger.info("Detected NPZ in ZIP: %s", npz_inside_zip)
                npz_path = output_npz_path or os.path.join(work_dir, 'file.npz')
                self.preprocess_existing_npz(
                    npz_path=npz_inside_zip,
                    output_npz_path=npz_path,
                    exam_modality=exam_modality,
                    category_hint=category_hint,
                    text_prompts=text_prompts,
                )
                if output_original_nifti_path:
                    self.convert_npz_to_nifti(
                        npz_path=npz_path,
                        output_nifti_path=output_original_nifti_path,
                    )
                self._set_ingestion_report(
                    {
                        'source': 'npz_zip_fallback',
                        'layout': 'npz',
                    }
                )
                return npz_path

            raise ValueError(
                "Unsupported ZIP content. Expected DICOM slices (canonical or non-canonical layout), "
                "or a .nii/.nii.gz/.npz file inside the ZIP."
            )

        except Exception as e:
            logger.error("ZIP input processing failed: %s", e, exc_info=True)
            raise ValueError(f"ZIP input processing failed: {e}")
        finally:
            # Best-effort cleanup of extracted DICOMs. The caller should still
            # cleanup the parent temp directory, but this helps avoid leaving
            # raw DICOMs behind if the caller forgets.
            try:
                if os.path.exists(extract_path):
                    shutil.rmtree(extract_path, ignore_errors=True)
            except Exception:
                logger.warning("Failed to cleanup extracted DICOMs", exc_info=True)

    def process(
        self,
        zip_path: str,
        text_prompts: dict,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> str:
        """
        Backward-compatible alias for ZIP → NPZ conversion.
        """
        return self.convert_zip_to_npz(
            zip_path=zip_path,
            text_prompts=text_prompts,
            exam_modality=exam_modality,
            category_hint=category_hint,
        )

    def convert_nifti_to_npz(
        self,
        nifti_path: str,
        text_prompts: dict | None = None,
        output_npz_path: str | None = None,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> str:
        """
        Convert NIfTI (.nii/.nii.gz) to a BiomedParse v2-compatible NPZ.

        The resulting NPZ matches the inference contract (`imgs`, `spacing`,
        `text_prompts`) with depth-first layout (Z,Y,X), consistent with ZIP
        DICOM uploads in this service.
        """
        if text_prompts is None:
            text_prompts = {}

        try:
            logger.info("Loading NIfTI file: %s", nifti_path)
            nifti_img = nib.load(nifti_path)
            volume_xyz = np.asanyarray(nifti_img.dataobj)
            volume_xyz = self._coerce_3d_volume(volume_xyz)

            # Canonicalize to depth-first layout used by DICOM path: (X,Y,Z) -> (Z,Y,X).
            volume = np.transpose(volume_xyz, (2, 1, 0))
            original_shape = tuple(volume.shape)

            spacing_xyz = tuple(float(v) for v in nifti_img.header.get_zooms()[:3])
            spacing_zyx = (spacing_xyz[2], spacing_xyz[1], spacing_xyz[0])

            volume = volume.astype(np.float32, copy=False)
            volume = self._normalize_intensity(
                volume=volume,
                exam_modality=exam_modality,
                category_hint=category_hint,
            )

            npz_path = output_npz_path or os.path.join(os.path.dirname(nifti_path), 'file.npz')
            self._save_npz(npz_path, volume, spacing_zyx, text_prompts)
            self._set_ingestion_report(
                {
                    'source': 'nifti_input',
                    'layout': 'nifti',
                    'effective_slices': int(volume.shape[0]) if volume.ndim >= 1 else None,
                    'matrix': [int(volume.shape[1]), int(volume.shape[2])] if volume.ndim == 3 else None,
                    'slice_spacing': float(spacing_zyx[0]) if len(spacing_zyx) >= 1 else None,
                }
            )

            logger.info("Converted NIfTI to NPZ shape %s -> %s", original_shape, tuple(volume.shape))
            return npz_path
        except Exception as e:
            logger.error("NIfTI conversion failed: %s", e, exc_info=True)
            raise ValueError(f"NIfTI conversion failed: {e}")

    def preprocess_existing_npz(
        self,
        npz_path: str,
        output_npz_path: str | None = None,
        exam_modality: str | None = None,
        category_hint: str | None = None,
        text_prompts: dict | None = None,
    ) -> str:
        """
        Normalize an uploaded NPZ to the inference-friendly contract.

        Input may contain image data in one of: imgs, image, images, data.
        Output is rewritten as:
        - imgs: 3D float32 volume with original shape preserved
        - spacing: preserved if present
        - text_prompts: preserved if present, otherwise injected from argument
        """
        with np.load(npz_path, allow_pickle=True) as data:
            image_key = next(
                (k for k in ['imgs', 'image', 'images', 'data'] if k in data.files),
                None,
            )
            if image_key is None:
                raise ValueError(
                    "NPZ must contain image data under one of keys: imgs, image, images, data"
                )

            volume = np.asarray(data[image_key])
            spacing = data['spacing'] if 'spacing' in data.files else None
            existing_text_prompts = data['text_prompts'] if 'text_prompts' in data.files else None

        volume = self._coerce_3d_volume(volume)
        original_shape = tuple(volume.shape)

        volume = volume.astype(np.float32, copy=False)
        volume = self._normalize_intensity(
            volume=volume,
            exam_modality=exam_modality,
            category_hint=category_hint,
        )

        payload = {'imgs': volume}
        if spacing is not None:
            payload['spacing'] = spacing
        normalized_existing_prompts = self._normalize_text_prompts(existing_text_prompts)
        effective_prompts = normalized_existing_prompts or (text_prompts or None)
        if effective_prompts is not None:
            payload['text_prompts'] = np.array(effective_prompts, dtype=object)

        out_path = output_npz_path or npz_path
        self._save_npz_payload(out_path, payload)
        self._set_ingestion_report(
            {
                'source': 'npz_input',
                'layout': 'npz',
                'effective_slices': int(volume.shape[0]) if volume.ndim >= 1 else None,
                'matrix': [int(volume.shape[1]), int(volume.shape[2])] if volume.ndim == 3 else None,
            }
        )

        logger.info("Preprocessed uploaded NPZ shape %s -> %s", original_shape, tuple(volume.shape))
        return out_path

    def convert_npz_to_nifti(
        self,
        npz_path: str,
        output_nifti_path: str,
    ) -> str:
        """
        Convert uploaded NPZ image volume to NIfTI preserving original resolution.
        """
        with np.load(npz_path, allow_pickle=True) as data:
            image_key = next(
                (k for k in ['imgs', 'image', 'images', 'data'] if k in data.files),
                None,
            )
            if image_key is None:
                raise ValueError(
                    "NPZ must contain image data under one of keys: imgs, image, images, data"
                )
            volume = np.asarray(data[image_key])
            spacing = data['spacing'] if 'spacing' in data.files else None

        volume = self._coerce_3d_volume(volume)
        self._save_volume_as_nifti(
            volume=volume,
            output_nifti_path=output_nifti_path,
            spacing_zyx=spacing,
        )
        return output_nifti_path
    
    @staticmethod
    def _unzip(zip_path: str, extract_to: str) -> str:
        """Unzip DICOM file."""
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_to)
        return extract_to

    @staticmethod
    def _find_first_file(base_dir: str, extensions: list[str]) -> str | None:
        """
        Find first file recursively by extension preference order.
        """
        for extension in extensions:
            lower_extension = extension.lower()
            for root, _dirs, files in os.walk(base_dir):
                for file_name in sorted(files):
                    if file_name.lower().endswith(lower_extension):
                        return os.path.join(root, file_name)
        return None

    @staticmethod
    def _normalize_nifti_to_gzip_file(
        input_nifti_path: str,
        output_nifti_path: str,
    ) -> None:
        """
        Save input NIfTI as a gzipped NIfTI destination, preserving affine/header.
        """
        image = nib.load(input_nifti_path)
        nib.save(image, output_nifti_path)
    
    @staticmethod
    def _get_study_folder(base_dir: str) -> str:
        """Get study folder from extracted DICOM."""
        dicom_root = os.path.join(base_dir, 'DICOM')
        if not os.path.isdir(dicom_root):
            raise ValueError("DICOM folder not found")
        
        study_folders = [
            os.path.join(dicom_root, d)
            for d in os.listdir(dicom_root)
            if os.path.isdir(os.path.join(dicom_root, d))
        ]
        
        if len(study_folders) != 1:
            raise ValueError(f"Expected 1 study folder, found {len(study_folders)}")
        
        return study_folders[0]
    
    @staticmethod
    def _get_series_folders(study_path: str) -> list:
        """Get series folders from study."""
        return sorted(
            [
                os.path.join(study_path, d)
                for d in os.listdir(study_path)
                if os.path.isdir(os.path.join(study_path, d))
            ]
        )

    @staticmethod
    def _safe_float(value, default: float | None = None) -> float | None:
        try:
            return float(value)
        except Exception:
            return default

    @staticmethod
    def _safe_int(value, default: int | None = None) -> int | None:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _get_slice_normal(ds) -> np.ndarray | None:
        iop = getattr(ds, 'ImageOrientationPatient', None)
        if iop is None or len(iop) < 6:
            return None
        try:
            row = np.array([float(iop[0]), float(iop[1]), float(iop[2])], dtype=np.float64)
            col = np.array([float(iop[3]), float(iop[4]), float(iop[5])], dtype=np.float64)
        except Exception:
            return None

        normal = np.cross(row, col)
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-8:
            return None
        return normal / norm

    @staticmethod
    def _slice_position_along_normal(ds, normal: np.ndarray | None) -> float | None:
        ipp = getattr(ds, 'ImagePositionPatient', None)
        if ipp is None or len(ipp) < 3 or normal is None:
            return None
        try:
            ipp_vec = np.array([float(ipp[0]), float(ipp[1]), float(ipp[2])], dtype=np.float64)
        except Exception:
            return None
        return float(np.dot(ipp_vec, normal))

    @staticmethod
    def _estimate_slice_spacing_from_positions(positions: list[float]) -> float | None:
        if len(positions) < 2:
            return None
        ordered = np.sort(np.array(positions, dtype=np.float64))
        diffs = np.diff(ordered)
        diffs = np.abs(diffs[np.abs(diffs) > 1e-6])
        if diffs.size == 0:
            return None
        return float(np.median(diffs))

    @classmethod
    def _build_probe_from_datasets(
        cls,
        datasets: list,
        *,
        path: str,
        label: str,
        files: list[str],
        series_uid: str | None = None,
    ) -> dict | None:
        if not datasets:
            return None

        first = datasets[0]
        normal = cls._get_slice_normal(first)
        positions: list[float] = []
        for ds in datasets:
            position = cls._slice_position_along_normal(ds, normal)
            if position is not None:
                positions.append(position)

        unique_positions = len({round(v, 4) for v in positions}) if positions else 0
        instance_numbers = [
            cls._safe_int(getattr(ds, 'InstanceNumber', None))
            for ds in datasets
        ]
        unique_instances = len({v for v in instance_numbers if v is not None})
        effective_slices = unique_positions or unique_instances or len(datasets)

        image_type_tokens = {
            str(token).strip().lower()
            for token in (getattr(first, 'ImageType', None) or [])
            if str(token).strip()
        }
        is_original = 'original' in image_type_tokens
        is_mpr_or_derived = 'mpr' in image_type_tokens or 'derived' in image_type_tokens

        rows = cls._safe_int(getattr(first, 'Rows', None), 0) or 0
        cols = cls._safe_int(getattr(first, 'Columns', None), 0) or 0
        slice_spacing = cls._estimate_slice_spacing_from_positions(positions)
        if slice_spacing is None:
            slice_spacing = cls._safe_float(getattr(first, 'SpacingBetweenSlices', None), None)
        if slice_spacing is None:
            slice_spacing = cls._safe_float(getattr(first, 'SliceThickness', None), None)

        series_description = str(getattr(first, 'SeriesDescription', '') or '').strip()

        # Prefer a volumetric series with many unique slice positions.
        # In ties, prefer ORIGINAL over DERIVED/MPR and finer slice spacing.
        spacing_score = 0.0
        if slice_spacing is not None and math.isfinite(slice_spacing) and slice_spacing > 0:
            spacing_score = -slice_spacing
        score = (
            effective_slices,
            1 if is_original else 0,
            0 if is_mpr_or_derived else 1,
            rows * cols,
            len(datasets),
            spacing_score,
        )

        return {
            'path': path,
            'label': label,
            'files': sorted(files),
            'series_uid': series_uid,
            'score': score,
            'effective_slices': effective_slices,
            'count': len(datasets),
            'rows': rows,
            'cols': cols,
            'slice_spacing': slice_spacing,
            'is_original': is_original,
            'is_mpr_or_derived': is_mpr_or_derived,
            'description': series_description,
        }

    @classmethod
    def _probe_series(cls, series_path: str) -> dict | None:
        files = sorted(
            os.path.join(series_path, file_name)
            for file_name in os.listdir(series_path)
            if os.path.isfile(os.path.join(series_path, file_name))
        )
        if not files:
            return None

        datasets = []
        accepted_files: list[str] = []
        for full_path in files:
            try:
                ds = pydicom.dcmread(full_path, stop_before_pixels=True, force=True)
                # Require core image geometry tags to avoid selecting non-image objects.
                if getattr(ds, 'Rows', None) is None or getattr(ds, 'Columns', None) is None:
                    continue
                datasets.append(ds)
                accepted_files.append(full_path)
            except Exception:
                continue

        series_uid = None
        if datasets:
            raw_uid = str(getattr(datasets[0], 'SeriesInstanceUID', '') or '').strip()
            series_uid = raw_uid or None

        return cls._build_probe_from_datasets(
            datasets,
            path=series_path,
            label=os.path.basename(series_path) or series_path,
            files=accepted_files,
            series_uid=series_uid,
        )

    @classmethod
    def _discover_dicom_series_probes(cls, base_dir: str) -> list[dict]:
        grouped: dict[str, dict] = {}

        for root, _dirs, files in os.walk(base_dir):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                try:
                    ds = pydicom.dcmread(full_path, stop_before_pixels=True, force=True)
                except Exception:
                    continue

                if getattr(ds, 'Rows', None) is None or getattr(ds, 'Columns', None) is None:
                    continue

                series_uid_raw = str(getattr(ds, 'SeriesInstanceUID', '') or '').strip()
                series_uid = series_uid_raw or None
                group_key = f"uid:{series_uid}" if series_uid else f"dir:{root}"

                if group_key not in grouped:
                    relative_root = os.path.relpath(root, base_dir)
                    label = f"SeriesUID:{series_uid}" if series_uid else relative_root
                    grouped[group_key] = {
                        'path': root,
                        'label': label,
                        'series_uid': series_uid,
                        'files': [],
                        'datasets': [],
                    }

                grouped[group_key]['files'].append(full_path)
                grouped[group_key]['datasets'].append(ds)

        probes: list[dict] = []
        for group in grouped.values():
            probe = cls._build_probe_from_datasets(
                group['datasets'],
                path=group['path'],
                label=group['label'],
                files=group['files'],
                series_uid=group['series_uid'],
            )
            if probe is not None:
                probes.append(probe)

        return probes

    @staticmethod
    def _log_probe_candidate(probe: dict, *, prefix: str) -> None:
        logger.info(
            (
                "%s %s: slices=%s files=%s matrix=%sx%s "
                "original=%s mpr_or_derived=%s spacing=%s desc=%s score=%s"
            ),
            prefix,
            str(probe.get('label') or probe.get('path') or '-'),
            probe.get('effective_slices'),
            probe.get('count'),
            probe.get('rows'),
            probe.get('cols'),
            probe.get('is_original'),
            probe.get('is_mpr_or_derived'),
            probe.get('slice_spacing'),
            probe.get('description') or '-',
            probe.get('score'),
        )

    @classmethod
    def _select_best_series_probe(cls, probes: list[dict]) -> dict:
        if not probes:
            raise ValueError("No valid DICOM image series found")

        for probe in probes:
            cls._log_probe_candidate(probe, prefix="Series candidate")

        probes_sorted = sorted(probes, key=lambda item: item.get('score', ()), reverse=True)
        selected = dict(probes_sorted[0])
        selected['candidate_count'] = len(probes_sorted)
        logger.info(
            "Selected series %s (%s slices, desc=%s)",
            str(selected.get('label') or selected.get('path') or '-'),
            selected.get('effective_slices'),
            selected.get('description') or '-',
        )
        return selected

    @classmethod
    def _select_best_series_probe_from_folders(cls, series_folders: list[str]) -> dict:
        probes = []
        for series_path in series_folders:
            probe = cls._probe_series(series_path)
            if probe is None:
                logger.info("Ignoring non-image series folder: %s", os.path.basename(series_path))
                continue
            probes.append(probe)
        return cls._select_best_series_probe(probes)

    @classmethod
    def _select_best_series_folder(cls, series_folders: list[str]) -> str:
        selected = cls._select_best_series_probe_from_folders(series_folders)
        return str(selected['path'])
    
    @staticmethod
    def _load_series(series_path: str) -> tuple:
        """Load DICOM series and return volume and spacing."""
        files = [
            os.path.join(series_path, file_name)
            for file_name in os.listdir(series_path)
        ]
        return DicomZipToNpzService._load_series_from_files(files, source_label=series_path)

    @staticmethod
    def _load_series_from_files(file_paths: list[str], source_label: str | None = None) -> tuple:
        slices = []

        for file_path in sorted(file_paths):
            try:
                ds = pydicom.dcmread(file_path, force=True)
                _ = ds.pixel_array
                slices.append(ds)
            except Exception:
                continue

        if not slices:
            source = source_label or 'discovered-series'
            raise ValueError(f"No DICOM slices found in {source}")

        # Sort slices by geometric position along the acquisition normal.
        normal = DicomZipToNpzService._get_slice_normal(slices[0])
        if normal is not None:
            slices_with_pos = []
            missing_pos = []
            for ds in slices:
                pos = DicomZipToNpzService._slice_position_along_normal(ds, normal)
                if pos is None:
                    missing_pos.append(ds)
                else:
                    slices_with_pos.append((pos, ds))

            if slices_with_pos:
                slices_with_pos.sort(key=lambda item: item[0])
                ordered = [ds for _, ds in slices_with_pos]
                if missing_pos:
                    missing_pos.sort(
                        key=lambda ds: DicomZipToNpzService._safe_int(
                            getattr(ds, 'InstanceNumber', 0),
                            0,
                        ) or 0
                    )
                    ordered.extend(missing_pos)
                slices = ordered
            else:
                try:
                    slices.sort(key=lambda ds: float(ds.ImagePositionPatient[2]))
                except Exception:
                    slices.sort(
                        key=lambda ds: DicomZipToNpzService._safe_int(
                            getattr(ds, 'InstanceNumber', 0),
                            0,
                        ) or 0
                    )
        else:
            try:
                slices.sort(key=lambda ds: float(ds.ImagePositionPatient[2]))
            except Exception:
                slices.sort(
                    key=lambda ds: DicomZipToNpzService._safe_int(
                        getattr(ds, 'InstanceNumber', 0),
                        0,
                    ) or 0
                )

        # Stack volume
        volume = np.stack([DicomZipToNpzService._extract_slice_pixels(s) for s in slices], axis=0)

        # Get spacing
        spacing = None
        try:
            px = slices[0].PixelSpacing
            spacing_y = float(px[0])
            spacing_x = float(px[1])

            positions = []
            if normal is not None:
                for ds in slices:
                    pos = DicomZipToNpzService._slice_position_along_normal(ds, normal)
                    if pos is not None:
                        positions.append(pos)
            spacing_z = DicomZipToNpzService._estimate_slice_spacing_from_positions(positions)
            if spacing_z is None:
                spacing_z = DicomZipToNpzService._safe_float(
                    getattr(slices[0], 'SpacingBetweenSlices', None),
                    None,
                )
            if spacing_z is None:
                spacing_z = DicomZipToNpzService._safe_float(
                    getattr(slices[0], 'SliceThickness', None),
                    None,
                )
            if spacing_z is None or spacing_z <= 0:
                spacing_z = 1.0

            spacing = (float(spacing_z), float(spacing_y), float(spacing_x))
        except Exception:
            pass

        return volume, spacing

    @staticmethod
    def _extract_slice_pixels(ds) -> np.ndarray:
        """
        Decode one DICOM slice into float32 intensities.

        CT slices must honor RescaleSlope/RescaleIntercept so downstream HU
        windowing matches the BiomedParse v2 recommendation.
        """
        pixels = np.asarray(ds.pixel_array, dtype=np.float32)

        slope_raw = getattr(ds, 'RescaleSlope', 1.0)
        intercept_raw = getattr(ds, 'RescaleIntercept', 0.0)
        try:
            slope = float(slope_raw)
        except Exception:
            slope = 1.0
        try:
            intercept = float(intercept_raw)
        except Exception:
            intercept = 0.0

        if slope != 1.0 or intercept != 0.0:
            pixels = (pixels * slope) + intercept

        return pixels.astype(np.float32, copy=False)
    
    def _preprocess(
        self,
        volume: np.ndarray,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> np.ndarray:
        """
        Preprocess volume for BiomedParse v2.

        Intensities are normalized into the expected [0, 255] range while the
        original spatial resolution is preserved for the model's own resize
        logic.
        """
        volume = volume.astype(np.float32, copy=False)
        volume = self._normalize_intensity(
            volume=volume,
            exam_modality=exam_modality,
            category_hint=category_hint,
        )
        return volume

    def _normalize_intensity(
        self,
        volume: np.ndarray,
        exam_modality: str | None = None,
        category_hint: str | None = None,
    ) -> np.ndarray:
        """
        Normalize intensities according to BiomedParse v2 guidance.

        - If already in [0, 255], keep as-is.
        - CT: apply HU window/level by anatomy then rescale to [0, 255].
        - Others: clip to [0.5th, 99.5th] percentile then rescale to [0, 255].
        """
        if volume.size == 0:
            return volume

        finite_mask = np.isfinite(volume)
        if not finite_mask.any():
            raise ValueError("Input volume has no finite intensity values")

        if not finite_mask.all():
            fill_value = float(np.min(volume[finite_mask]))
            volume = np.where(finite_mask, volume, fill_value).astype(np.float32, copy=False)

        min_value = float(np.min(volume))
        max_value = float(np.max(volume))
        if min_value >= 0.0 and max_value <= 255.0:
            logger.info("Skipping intensity normalization (already within [0,255])")
            return volume.astype(np.float32, copy=False)

        modality = str(exam_modality or '').strip().lower()
        if modality == 'ct':
            width, level = self._resolve_ct_window(category_hint=category_hint)
            low = level - (width / 2.0)
            high = level + (width / 2.0)
            clipped = np.clip(volume, low, high)
            logger.info(
                "Applying CT windowing [%s, %s] from preset (%s) before rescale to [0,255]",
                low,
                high,
                self._resolve_ct_window_preset_name(category_hint=category_hint),
            )
            return self._rescale_to_255(clipped, source_min=low, source_max=high)

        p_low, p_high = np.percentile(volume, [0.5, 99.5])
        if not np.isfinite(p_low) or not np.isfinite(p_high):
            p_low = min_value
            p_high = max_value
        if p_high <= p_low:
            logger.warning("Invalid percentile bounds (%s, %s); clipping directly to [0,255]", p_low, p_high)
            return np.clip(volume, 0.0, 255.0).astype(np.float32, copy=False)

        clipped = np.clip(volume, p_low, p_high)
        logger.info("Applying percentile clipping [%.4f, %.4f] before rescale to [0,255]", p_low, p_high)
        return self._rescale_to_255(clipped, source_min=float(p_low), source_max=float(p_high))
    
    def _resize_xy(self, volume: np.ndarray) -> np.ndarray:
        """Legacy no-op kept for backwards compatibility."""
        return volume
    
    def _resample_slices(self, volume: np.ndarray) -> np.ndarray:
        """Legacy no-op kept for backwards compatibility."""
        return volume
    
    def _resolve_ct_window(self, category_hint: str | None) -> tuple[float, float]:
        """Resolve CT window (width, level) from anatomy hint."""
        preset_name = self._resolve_ct_window_preset_name(category_hint=category_hint)
        preset = self.ct_windows[preset_name]
        return float(preset['width']), float(preset['level'])

    def _resolve_ct_window_preset_name(self, category_hint: str | None) -> str:
        """Resolve one of: soft_tissues, lung, brain, bone."""
        text = str(category_hint or '').strip().lower()
        if any(token in text for token in ['lung', 'pulmo', 'covid', 'chest', 'thorax', 'torax']):
            return 'lung'
        if any(token in text for token in ['brain', 'neuro', 'stroke', 'intracran', 'cranial']):
            return 'brain'
        if any(token in text for token in ['bone', 'osse', 'skelet', 'spine', 'vertebra', 'fracture']):
            return 'bone'
        return 'soft_tissues'

    @staticmethod
    def _rescale_to_255(volume: np.ndarray, source_min: float, source_max: float) -> np.ndarray:
        """Rescale intensities from [source_min, source_max] into [0, 255]."""
        span = float(source_max - source_min)
        if span <= 1e-8:
            return np.clip(volume, 0.0, 255.0).astype(np.float32, copy=False)
        scaled = (volume - source_min) / span
        scaled = scaled * 255.0
        return np.clip(scaled, 0.0, 255.0).astype(np.float32, copy=False)

    @staticmethod
    def _save_volume_as_nifti(
        volume: np.ndarray,
        output_nifti_path: str,
        spacing_zyx=None,
    ) -> None:
        """
        Save a 3D volume as NIfTI with canonical axis order (X,Y,Z).

        Internal pipeline stores volumes in (Z,Y,X). Viewer-oriented NIfTI
        should be exported as (X,Y,Z) to avoid distorted orthogonal views.
        """
        volume_3d = DicomZipToNpzService._coerce_3d_volume(np.asarray(volume))
        volume_3d = volume_3d.astype(np.float32, copy=False)
        volume_xyz = np.transpose(volume_3d, (2, 1, 0))

        spacing_xyz = None
        if spacing_zyx is not None:
            spacing_arr = np.asarray(spacing_zyx).reshape(-1)
            if spacing_arr.size >= 3:
                spacing_xyz = (
                    float(spacing_arr[2]),
                    float(spacing_arr[1]),
                    float(spacing_arr[0]),
                )

        affine = np.eye(4, dtype=np.float32)
        if spacing_xyz is not None:
            affine[0, 0] = spacing_xyz[0]
            affine[1, 1] = spacing_xyz[1]
            affine[2, 2] = spacing_xyz[2]

        nii = nib.Nifti1Image(volume_xyz, affine)
        if spacing_xyz is not None:
            try:
                nii.header.set_zooms(spacing_xyz)
            except Exception:
                logger.warning("Failed to set NIfTI zooms for original volume", exc_info=True)

        nib.save(nii, output_nifti_path)
        logger.info(
            "Saved original-resolution NIfTI: %s shape_zyx=%s shape_xyz=%s spacing_xyz=%s",
            output_nifti_path,
            tuple(volume_3d.shape),
            tuple(volume_xyz.shape),
            spacing_xyz,
        )

    @staticmethod
    def _coerce_3d_volume(volume: np.ndarray) -> np.ndarray:
        """
        Coerce common singleton-channel layouts into (Z, H, W).
        """
        if volume.ndim == 3:
            return volume

        squeezed = np.squeeze(volume)
        if squeezed.ndim == 3:
            return squeezed

        raise ValueError(f"Expected a 3D volume, got shape {tuple(volume.shape)}")

    @staticmethod
    def _save_npz_payload(npz_path: str, payload: dict) -> None:
        """
        Save NPZ atomically to avoid partial files.
        """
        tmp_path = None
        try:
            tmp_file = tempfile.NamedTemporaryFile(
                dir=os.path.dirname(npz_path) or '.',
                suffix='.npz',
                delete=False,
            )
            tmp_path = tmp_file.name
            tmp_file.close()

            np.savez_compressed(tmp_path, **payload)
            os.replace(tmp_path, npz_path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    
    @staticmethod
    def _save_npz(npz_path: str, volume: np.ndarray, spacing, text_prompts: dict):
        """Save NPZ file following the BiomedParse v2 contract."""
        payload = {
            'imgs': np.asarray(volume, dtype=np.float32),
            'text_prompts': np.array(text_prompts or {}, dtype=object),
        }
        if spacing is not None:
            payload['spacing'] = np.asarray(spacing)
        DicomZipToNpzService._save_npz_payload(npz_path, payload)

    @staticmethod
    def _normalize_text_prompts(raw_value):
        """
        Normalize NPZ-loaded text_prompts payload to a dict when possible.
        """
        if raw_value is None:
            return None

        value = raw_value
        if isinstance(value, np.ndarray) and value.dtype == object:
            if value.shape == ():
                try:
                    value = value.item()
                except Exception:
                    return None
            elif value.size == 1:
                try:
                    value = value.reshape(()).item()
                except Exception:
                    return None

        if isinstance(value, dict):
            return value
        return None


def cleanup_temp_files(temp_dir: str):
    """Clean up temporary files."""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp dir: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp dir: {e}")
