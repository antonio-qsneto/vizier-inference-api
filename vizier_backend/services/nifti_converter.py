"""
Convert NPZ results to NIfTI format.
Supports converting image and segmentation artifacts separately.
"""

import numpy as np
import nibabel as nib
import logging
import os

logger = logging.getLogger(__name__)


class NiftiConverter:
    """Convert NPZ files to NIfTI format (image or segmentation)."""

    @staticmethod
    def _log_array_stats(name: str, arr: np.ndarray) -> None:
        arr_safe = arr.astype(np.float32, copy=False)
        logger.info(
            "%s stats: shape=%s dtype=%s min=%s max=%s mean=%s std=%s nonzero=%s",
            name,
            tuple(arr.shape),
            str(arr.dtype),
            float(np.min(arr_safe)),
            float(np.max(arr_safe)),
            float(np.mean(arr_safe)),
            float(np.std(arr_safe)),
            int(np.count_nonzero(arr_safe)),
        )

    @staticmethod
    def _convert_dtype(arr: np.ndarray) -> np.ndarray:
        """
        Ensure NIfTI-compatible dtypes.

        NIfTI-1 does not support float16. Keep floats as float32.
        """
        if np.issubdtype(arr.dtype, np.bool_):
            return arr.astype(np.uint8)
        if arr.dtype == np.float16:
            logger.info("Converting float16 -> float32 for NIfTI compatibility")
            return arr.astype(np.float32)
        if np.issubdtype(arr.dtype, np.floating):
            return arr.astype(np.float32)
        if np.issubdtype(arr.dtype, np.integer):
            return arr.astype(np.int16)
        raise TypeError(f"Unsupported dtype: {arr.dtype}")

    @staticmethod
    def _maybe_rescale_for_visualization(imgs: np.ndarray) -> np.ndarray:
        """
        Rescale normalized floating volumes to [0, 255] for viewer friendliness.
        Does nothing for near-CT/HU-like ranges.
        """
        if not np.issubdtype(imgs.dtype, np.floating):
            return imgs

        imgs_f = imgs.astype(np.float32, copy=False)
        min_val = float(np.min(imgs_f))
        max_val = float(np.max(imgs_f))
        value_range = max_val - min_val

        if value_range == 0:
            logger.warning("Zero intensity range; skipping rescale")
            return imgs_f

        # Heuristic: small-range floating values are typically z-scored/normalized.
        if min_val >= -10.0 and max_val <= 10.0:
            logger.info("Rescaling intensities to [0, 255] for visualization")
            scaled = (imgs_f - min_val) / value_range
            scaled = scaled * 255.0
            return scaled.astype(np.float32)

        return imgs_f

    @staticmethod
    def _normalize_spacing(spacing) -> tuple[float, float, float] | None:
        """
        Normalize spacing to a (s0, s1, s2) float tuple matching the data axes.
        """
        if spacing is None:
            return None

        spacing_arr = np.asarray(spacing).reshape(-1)
        if spacing_arr.size < 3:
            return None

        try:
            return (float(spacing_arr[0]), float(spacing_arr[1]), float(spacing_arr[2]))
        except Exception:
            return None

    @staticmethod
    def segs_npz_to_nifti(npz_path: str, output_path: str, spacing=None) -> bool:
        """
        Convert a segmentation NPZ (expected key: 'segs') to a 3D NIfTI labelmap.

        This is a mask-only conversion: it does not join/stack with the image.
        """
        try:
            logger.info("Loading segmentation NPZ from: %s", npz_path)
            with np.load(npz_path, allow_pickle=True) as data:
                if spacing is None:
                    spacing = data['spacing'] if 'spacing' in data.files else None
                spacing_tuple = NiftiConverter._normalize_spacing(spacing) or (1.0, 1.0, 1.0)

                segs = None
                if 'segs' in data.files:
                    segs = data['segs']
                    logger.info("Found segmentation data in key 'segs'")
                else:
                    for key in ['mask', 'pred_mask', 'labels', 'output', 'prediction', 'imgs', 'result']:
                        if key in data.files:
                            segs = data[key]
                            logger.info("Using segmentation data from key '%s' (fallback)", key)
                            break

                if segs is None:
                    raise KeyError("NPZ must contain 'segs' (or a supported fallback key)")

            logger.info("Segmentation shape=%s dtype=%s", tuple(segs.shape), str(segs.dtype))

            # Remove singleton channel (e.g., (1, Z, Y, X) or (Z, Y, X, 1))
            if segs.ndim == 4 and segs.shape[0] == 1:
                logger.info("Removing singleton channel dimension from segs (axis 0)")
                segs = segs[0]
            if segs.ndim == 4 and segs.shape[-1] == 1:
                logger.info("Removing singleton channel dimension from segs (last axis)")
                segs = segs[..., 0]

            if segs.ndim != 3:
                raise ValueError(f"Expected 3D segmentation volume, got shape {segs.shape}")

            # Ensure integer mask type
            segs = segs.astype(np.uint8, copy=False)
            NiftiConverter._log_array_stats("segs_labelmap", segs)

            affine = np.eye(4)
            affine[0, 0] = spacing_tuple[0]
            affine[1, 1] = spacing_tuple[1]
            affine[2, 2] = spacing_tuple[2]

            nii_img = nib.Nifti1Image(segs, affine)
            try:
                nii_img.header.set_zooms(tuple(spacing_tuple[:3]))
            except Exception:
                logger.warning("Failed to set header zooms", exc_info=True)

            nib.save(nii_img, output_path)
            logger.info("Saved segmentation NIfTI: %s (%s bytes)", output_path, os.path.getsize(output_path))
            return True

        except Exception as e:
            logger.error("Failed to convert segs NPZ to NIfTI: %s", e, exc_info=True)
            return False
    
    @staticmethod
    def npz_to_nifti(npz_path: str, output_path: str, spacing=None, mask_npz_path=None) -> bool:
        """
        Convert NPZ file to NIfTI format.
        Converts image NPZ into a visualization-friendly 3D NIfTI.
        
        Args:
            npz_path: Path to input NPZ file (original image)
            output_path: Path to output NIfTI file
            spacing: Voxel spacing (optional)
            mask_npz_path: Deprecated (ignored). Use `segs_npz_to_nifti` for masks.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if mask_npz_path:
                logger.warning("mask_npz_path is ignored; use segs_npz_to_nifti for segmentation conversion")

            # Load original image
            logger.info(f"Loading original image from: {npz_path}")
            with np.load(npz_path, allow_pickle=True) as data:
                # Extract image data
                imgs = None
                for key in ['imgs', 'image', 'images', 'data']:
                    if key in data.files:
                        imgs = data[key]
                        logger.info(f"Found image data in key '{key}'")
                        break
                
                if imgs is None:
                    available_keys = list(data.files)
                    logger.warning(f"No known image key found. Available keys: {available_keys}")
                    if available_keys:
                        imgs = data[available_keys[0]]
                        logger.info(f"Using first available key: '{available_keys[0]}'")
                    else:
                        raise ValueError("No image data found in NPZ file")
                
                # Get spacing from original image if available
                if spacing is None:
                    spacing = data['spacing'] if 'spacing' in data.files else None
                spacing_tuple = NiftiConverter._normalize_spacing(spacing)

            logger.info("Original image shape: %s", tuple(imgs.shape))

            # Remove singleton channel dimension if present (e.g., (1, Z, Y, X) -> (Z, Y, X))
            if imgs.ndim == 4 and imgs.shape[0] == 1:
                logger.info("Removing singleton channel dimension from image")
                imgs = imgs[0]
            if imgs.ndim == 4 and imgs.shape[-1] == 1:
                logger.info("Removing trailing singleton channel dimension from image")
                imgs = imgs[..., 0]

            if imgs.ndim != 3:
                raise ValueError(f"Expected 3D image volume, got shape {imgs.shape}")

            # Ensure NIfTI-compatible dtype and stable stats
            imgs = NiftiConverter._convert_dtype(imgs)
            NiftiConverter._log_array_stats("image_before_rescale", imgs)

            # Rescale for visualization (apply only to image channel)
            imgs = NiftiConverter._maybe_rescale_for_visualization(imgs)
            NiftiConverter._log_array_stats("image_final", imgs)
            
            # Create affine matrix (match spacing order to data axes)
            affine = np.eye(4)
            if spacing_tuple is not None:
                affine[0, 0] = spacing_tuple[0]
                affine[1, 1] = spacing_tuple[1]
                affine[2, 2] = spacing_tuple[2]
            
            # Create NIfTI image
            logger.info(f"Creating NIfTI image with shape: {imgs.shape}")
            nifti_img = nib.Nifti1Image(imgs, affine)

            # Preserve spacing in header
            if spacing_tuple is not None:
                zooms = list(spacing_tuple[:3])
                if imgs.ndim > 3:
                    zooms += [1.0] * (imgs.ndim - 3)
                try:
                    nifti_img.header.set_zooms(tuple(zooms))
                except Exception:
                    logger.warning("Failed to set header zooms", exc_info=True)
            
            # Save
            nib.save(nifti_img, output_path)
            logger.info(f"Converted to NIfTI: {output_path} ({os.path.getsize(output_path)} bytes)")
            return True
        
        except Exception as e:
            logger.error(f"Failed to convert NPZ to NIfTI: {e}", exc_info=True)
            return False
