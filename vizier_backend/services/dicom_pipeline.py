"""
DICOM to NPZ conversion pipeline.
Handles ZIP extraction, DICOM loading, preprocessing, and NPZ creation.
"""

import os
import shutil
import tempfile
import zipfile
import numpy as np
import pydicom
import cv2
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class DicomZipToNpzService:
    """Service for converting DICOM ZIP to NPZ format."""
    
    def __init__(self):
        self.target_hw = settings.DICOM_TARGET_HW
        self.target_slices = settings.DICOM_TARGET_SLICES
        self.window_center = settings.DICOM_WINDOW_CENTER
        self.window_width = settings.DICOM_WINDOW_WIDTH
    
    def convert_zip_to_npz(
        self,
        zip_path: str,
        text_prompts: dict | None = None,
        output_npz_path: str | None = None,
    ) -> str:
        """
        Convert a DICOM ZIP file into a single NPZ file.

        This method is intentionally side-effect light: it extracts into a
        subfolder next to the ZIP path so the caller can cleanup the parent
        temp directory (common in DRF upload flows).

        Args:
            zip_path: Path to the input DICOM ZIP file.
            text_prompts: Dict with prompts for inference (stored into NPZ).
            output_npz_path: Optional explicit output path for the generated NPZ.

        Returns:
            Path to the generated NPZ file.

        Raises:
            ValueError: If processing fails.
        """
        if text_prompts is None:
            text_prompts = {}

        work_dir = os.path.dirname(zip_path)
        extract_path = os.path.join(work_dir, 'extracted')

        try:
            logger.info(f"Processing DICOM ZIP: {zip_path}")

            # Ensure a clean extraction directory (caller usually controls work_dir)
            if os.path.exists(extract_path):
                shutil.rmtree(extract_path, ignore_errors=True)
            os.makedirs(extract_path, exist_ok=True)

            # Unzip
            self._unzip(zip_path, extract_path)

            # Get study folder
            study_path = self._get_study_folder(extract_path)

            # Get series folders
            series_folders = self._get_series_folders(study_path)
            if not series_folders:
                raise ValueError("No series folders found")

            # Use first series
            series_path = series_folders[0]
            logger.info(f"Using series: {os.path.basename(series_path)}")

            # Load series
            volume, spacing = self._load_series(series_path)
            logger.info(f"Loaded volume shape: {volume.shape}")

            # Preprocess
            volume = self._preprocess(volume)
            logger.info(f"Preprocessed volume shape: {volume.shape}")

            # Create NPZ
            npz_path = output_npz_path or os.path.join(work_dir, 'file.npz')
            self._save_npz(npz_path, volume, spacing, text_prompts)
            logger.info(f"Saved NPZ: {npz_path}")

            return npz_path

        except Exception as e:
            logger.error(f"DICOM processing failed: {e}", exc_info=True)
            raise ValueError(f"DICOM processing failed: {e}")
        finally:
            # Best-effort cleanup of extracted DICOMs. The caller should still
            # cleanup the parent temp directory, but this helps avoid leaving
            # raw DICOMs behind if the caller forgets.
            try:
                if os.path.exists(extract_path):
                    shutil.rmtree(extract_path, ignore_errors=True)
            except Exception:
                logger.warning("Failed to cleanup extracted DICOMs", exc_info=True)

    def process(self, zip_path: str, text_prompts: dict) -> str:
        """
        Backward-compatible alias for ZIP → NPZ conversion.
        """
        return self.convert_zip_to_npz(zip_path=zip_path, text_prompts=text_prompts)

    def preprocess_existing_npz(
        self,
        npz_path: str,
        output_npz_path: str | None = None,
    ) -> str:
        """
        Normalize an uploaded NPZ to the inference-friendly contract.

        Input may contain image data in one of: imgs, image, images, data.
        Output is rewritten as:
        - imgs: 3D float16 volume resized to target HW and target slices
        - spacing: preserved if present
        - text_prompts: preserved if present
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
            text_prompts = data['text_prompts'] if 'text_prompts' in data.files else None

        volume = self._coerce_3d_volume(volume)
        original_shape = tuple(volume.shape)

        volume = volume.astype(np.float32, copy=False)
        volume = self._resize_xy(volume)
        volume = self._resample_slices(volume)
        volume = volume.astype(np.float16, copy=False)

        payload = {'imgs': volume}
        if spacing is not None:
            payload['spacing'] = spacing
        if text_prompts is not None:
            payload['text_prompts'] = text_prompts

        out_path = output_npz_path or npz_path
        self._save_npz_payload(out_path, payload)

        logger.info("Preprocessed uploaded NPZ shape %s -> %s", original_shape, tuple(volume.shape))
        return out_path
    
    @staticmethod
    def _unzip(zip_path: str, extract_to: str) -> str:
        """Unzip DICOM file."""
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_to)
        return extract_to
    
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
        return [
            os.path.join(study_path, d)
            for d in os.listdir(study_path)
            if os.path.isdir(os.path.join(study_path, d))
        ]
    
    @staticmethod
    def _load_series(series_path: str) -> tuple:
        """Load DICOM series and return volume and spacing."""
        slices = []
        
        for f in os.listdir(series_path):
            fp = os.path.join(series_path, f)
            try:
                ds = pydicom.dcmread(fp)
                if hasattr(ds, 'pixel_array'):
                    slices.append(ds)
            except Exception:
                continue
        
        if not slices:
            raise ValueError(f"No DICOM slices found in {series_path}")
        
        # Sort slices
        try:
            slices.sort(key=lambda s: float(s.ImagePositionPatient[2]))
        except Exception:
            try:
                slices.sort(key=lambda s: int(s.InstanceNumber))
            except Exception:
                pass
        
        # Stack volume
        volume = np.stack([s.pixel_array for s in slices], axis=0)
        
        # Get spacing
        spacing = None
        try:
            px = slices[0].PixelSpacing
            th = slices[0].SliceThickness
            spacing = (float(th), float(px[0]), float(px[1]))
        except Exception:
            pass
        
        return volume, spacing
    
    def _preprocess(self, volume: np.ndarray) -> np.ndarray:
        """Preprocess volume."""
        volume = volume.astype(np.float32)
        volume = self._windowing(volume)
        volume = self._resize_xy(volume)
        volume = self._resample_slices(volume)
        volume = self._normalize(volume)
        volume = volume.astype(np.float16)
        return volume
    
    def _windowing(self, volume: np.ndarray) -> np.ndarray:
        """Apply windowing."""
        min_v = self.window_center - self.window_width // 2
        max_v = self.window_center + self.window_width // 2
        volume = np.clip(volume, min_v, max_v)
        volume = (volume - min_v) / (max_v - min_v)
        return volume
    
    def _resize_xy(self, volume: np.ndarray) -> np.ndarray:
        """Resize XY dimensions."""
        return np.stack([
            cv2.resize(slice_, self.target_hw, interpolation=cv2.INTER_AREA)
            for slice_ in volume
        ])
    
    def _resample_slices(self, volume: np.ndarray) -> np.ndarray:
        """Resample Z dimension."""
        if volume.shape[0] <= self.target_slices:
            return volume
        idx = np.linspace(0, volume.shape[0] - 1, self.target_slices).astype(int)
        return volume[idx]
    
    @staticmethod
    def _normalize(volume: np.ndarray) -> np.ndarray:
        """Normalize volume."""
        mean = volume.mean()
        std = volume.std()
        return (volume - mean) / (std + 1e-8)

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
        """Save NPZ file."""
        np.savez_compressed(
            npz_path,
            imgs=volume,
            spacing=spacing,
            text_prompts=np.array(text_prompts, dtype=object)
        )


def cleanup_temp_files(temp_dir: str):
    """Clean up temporary files."""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp dir: {temp_dir}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp dir: {e}")
