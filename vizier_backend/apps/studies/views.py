"""
Views for studies app.
"""

import json
import os
import tempfile
import shutil
from pathlib import Path
import numpy as np
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone
from .models import Study, Job
from .serializers import StudySerializer, StudyCreateSerializer, StudyStatusSerializer, StudyResultSerializer
from apps.accounts.permissions import TenantQuerySetMixin
from apps.audit.services import AuditService
from services.dicom_pipeline import DicomZipToNpzService, cleanup_temp_files
from services.s3_utils import S3Utils
from services.nifti_converter import NiftiConverter
from apps.inference.client import InferenceClient
import logging

logger = logging.getLogger(__name__)


class StudyViewSet(TenantQuerySetMixin, viewsets.ModelViewSet):
    """ViewSet for Study model."""
    
    queryset = Study.objects.all()
    serializer_class = StudySerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    
    @action(detail=False, methods=['post'], parser_classes=(MultiPartParser, FormParser))
    def upload(self, request):
        """
        Upload DICOM ZIP file and start processing.
        POST /api/studies/upload/
        """
        return self.create(request)
    
    def create(self, request, *args, **kwargs):
        """
        Create a new study from DICOM ZIP upload.
        """
        serializer = StudyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Access rules:
        # - clinic users: studies are attached to their clinic
        # - INDIVIDUAL users: studies are personal and clinic-less
        if not request.user.clinic and request.user.role != 'INDIVIDUAL':
            return Response(
                {'error': 'User must belong to a clinic'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        temp_dir = None
        study = None
        try:
            upload_file = serializer.validated_data.get('upload_file')
            upload_type = serializer.validated_data.get('upload_type')

            # Create temp directory for processing
            temp_dir = tempfile.mkdtemp(prefix='dicom_')
            logger.info(f"Created temp directory: {temp_dir}")

            # Resolve category (name + prompt)
            category_id = serializer.validated_data.get('category_id') or ''
            category_name, prompt_text = self._resolve_category_and_prompt(category_id)
            text_prompts = {"1": prompt_text, "instance_label": 0}

            npz_path = os.path.join(temp_dir, 'file.npz')

            if upload_type == 'zip':
                # Save uploaded ZIP
                zip_filename = os.path.basename(getattr(upload_file, 'name', 'dicom.zip') or 'dicom.zip')
                zip_path = os.path.join(temp_dir, zip_filename)
                with open(zip_path, 'wb') as f:
                    for chunk in upload_file.chunks():
                        f.write(chunk)
                logger.info(f"Saved uploaded ZIP: {zip_path}")

                # Convert DICOM ZIP to NPZ
                logger.info(f"Converting DICOM ZIP to NPZ: {zip_path}")
                dicom_service = DicomZipToNpzService()
                npz_path = dicom_service.convert_zip_to_npz(
                    zip_path=zip_path,
                    text_prompts=text_prompts,
                    output_npz_path=npz_path,
                )
                logger.info(f"Converted to NPZ: {npz_path} ({os.path.getsize(npz_path)} bytes)")

            elif upload_type == 'npz':
                # Save uploaded NPZ
                with open(npz_path, 'wb') as f:
                    for chunk in upload_file.chunks():
                        f.write(chunk)
                logger.info(f"Saved uploaded NPZ: {npz_path}")

                # Validate NPZ has expected structure (without loading full arrays)
                with np.load(npz_path, allow_pickle=True) as data:
                    keys = set(data.files)
                if not keys.intersection({'imgs', 'image', 'images', 'data'}):
                    raise ValueError(
                        "NPZ must contain image data under one of keys: imgs, image, images, data"
                    )

                # Ensure prompts exist for inference contract (only if missing)
                self._ensure_npz_text_prompts(npz_path=npz_path, text_prompts=text_prompts)

            else:
                raise ValueError(f"Unsupported upload_type: {upload_type}")
            
            # Create Study record
            try:
                study = Study.objects.create(
                    clinic=request.user.clinic if request.user.clinic else None,
                    owner=request.user,
                    category=category_name,
                    status='SUBMITTED',
                )
            except IntegrityError as exc:
                if (
                    request.user.role == 'INDIVIDUAL'
                    and not getattr(request.user, 'clinic_id', None)
                    and 'clinic_id' in str(exc)
                    and 'violates not-null constraint' in str(exc)
                ):
                    raise ValueError(
                        "Database schema is out of date (Study.clinic must be nullable). "
                        "Run `python manage.py migrate` and restart the server."
                    ) from exc
                raise
            logger.info(f"Created Study: {study.id}")

            if getattr(settings, 'SAVE_ANALYSIS_ARTIFACTS', False):
                analysis_dir = self._get_analysis_dir(study_id=str(study.id))
                analysis_dir.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(npz_path, analysis_dir / "file.npz")
                    logger.info(f"Saved analysis original NPZ: {analysis_dir / 'file.npz'}")
                except Exception:
                    logger.warning("Failed to save analysis original NPZ", exc_info=True)
            
            # Save original NPZ to storage (for later JOIN with mask)
            s3_utils = S3Utils()
            owner_scope = study.get_owner_scope()
            original_npz_key = f"uploads/{owner_scope}/{study.id}/file.npz"
            logger.info(f"Saving original NPZ to storage: {original_npz_key}")
            
            if not s3_utils.upload_file(npz_path, original_npz_key, 'application/octet-stream'):
                raise Exception(f"Failed to save original NPZ to storage")
            logger.info(f"Original NPZ saved to storage")
            
            # Submit to inference API
            logger.info(f"Submitting NPZ to inference API: {npz_path}")
            inference_client = InferenceClient()
            external_job_id = inference_client.submit_job(npz_path)
            logger.info(f"Submitted to inference API, job_id: {external_job_id}")
            
            # Create Job record
            job = Job.objects.create(
                study=study,
                external_job_id=external_job_id,
                status='SUBMITTED'
            )
            study.inference_job_id = external_job_id
            study.status = 'PROCESSING'
            study.save()
            logger.info(f"Created Job: {job.id}")
            
            # Log audit
            AuditService.log_study_submit(study)
            
            logger.info(f"Study processing started: {study.id}")
            
            # Cleanup temp files
            cleanup_temp_files(temp_dir)
            
            response_serializer = StudySerializer(study)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Failed to upload and process DICOM: {e}", exc_info=True)
            if study is not None:
                try:
                    study.mark_failed(str(e))
                except Exception:
                    logger.warning("Failed to mark study as FAILED", exc_info=True)
            if temp_dir:
                cleanup_temp_files(temp_dir)
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """
        Get study status and job progress.
        Automatically creates result file when status becomes COMPLETED.
        """
        study = self.get_object()
        
        # Check permission
        if request.user.clinic:
            allowed = study.clinic == request.user.clinic
        else:
            allowed = study.owner_id == request.user.id

        if not allowed:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Get job status from inference API
            if study.inference_job_id:
                inference_client = InferenceClient()
                job_status = inference_client.get_status(study.inference_job_id)

                raw_status = str(job_status.get('status') or '').strip()
                normalized_status = raw_status.lower()
                status_map = {
                    'pending': 'SUBMITTED',
                    'running': 'PROCESSING',
                    'completed': 'COMPLETED',
                    'failed': 'FAILED',
                    'queued': 'QUEUED',
                    'processing': 'PROCESSING',
                }
                mapped_status = status_map.get(
                    normalized_status,
                    raw_status.upper() if raw_status else 'UNKNOWN',
                )
                
                # Update local job status
                if study.job:
                    study.job.update_status(
                        mapped_status,
                        job_status.get('progress')
                    )
                
                # Update study status if completed
                if mapped_status == 'COMPLETED' and study.status != 'COMPLETED':
                    study.status = 'COMPLETED'
                    study.completed_at = timezone.now()
                    study.save()
                    logger.info(f"Study completed, creating visualization files for: {study.id}")
                    self._create_result_file(study)
                elif mapped_status == 'FAILED' and study.status != 'FAILED':
                    study.status = 'FAILED'
                    study.completed_at = timezone.now()
                    study.save()
            
            # Log audit
            AuditService.log_study_status_check(study)
            
            serializer = StudyStatusSerializer(study)
            return Response(serializer.data)
        
        except Exception as e:
            logger.error(f"Failed to get status: {e}", exc_info=True)
            payload = {'error': 'Failed to get status'}
            if settings.DEBUG:
                payload['detail'] = str(e)
            return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def analysis_files(self, request, pk=None):
        """
        Get all analysis files (original NPZ, mask NPZ, visualization NIfTI files) in a single folder.
        Returns path to analysis folder for investigation.
        """
        study = self.get_object()
        s3_utils = S3Utils()
        
        try:
            # Create analysis folder
            analysis_dir = self._get_analysis_dir(study_id=str(study.id))
            analysis_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created analysis directory: {analysis_dir}")
            
            # 1. Download original NPZ (file.npz)
            owner_scope = study.get_owner_scope()
            original_npz_key_candidates = [
                f"uploads/{owner_scope}/{study.id}/file.npz",
                f"uploads/{owner_scope}/{study.id}/input.npz",  # legacy
            ]
            original_npz_key = next(
                (k for k in original_npz_key_candidates if s3_utils.object_exists(k)),
                original_npz_key_candidates[0],
            )
            original_npz_path = analysis_dir / "file.npz"
            
            if s3_utils.object_exists(original_npz_key):
                if s3_utils.download_file(original_npz_key, str(original_npz_path)):
                    logger.info(f"Downloaded original NPZ: {original_npz_path}")
                else:
                    logger.warning(f"Failed to download original NPZ: {original_npz_key}")
            else:
                logger.warning(f"Original NPZ not found: {original_npz_key}")
            
            # 2. Download mask NPZ (mask.npz from API)
            # We need to download from API again
            inference_client = InferenceClient()
            mask_npz_path = analysis_dir / "mask.npz"
            
            try:
                if study.job and study.job.external_job_id:
                    logger.info(f"Downloading mask from API for job: {study.job.external_job_id}")
                    if inference_client.get_results(study.job.external_job_id, str(mask_npz_path)):
                        logger.info(f"Downloaded mask NPZ: {mask_npz_path}")
                    else:
                        logger.warning(f"Failed to download mask NPZ")
            except Exception as e:
                logger.warning(f"Could not download mask: {e}")
            
            # 3. Download visualization NIfTI files (image.nii.gz + mask.nii.gz)
            default_image_key = f"results/{owner_scope}/{study.id}/image.nii.gz"
            default_mask_key = f"results/{owner_scope}/{study.id}/mask.nii.gz"
            image_nifti_key = study.image_s3_key or default_image_key
            mask_nifti_key = study.mask_s3_key or default_mask_key

            image_nifti_path = analysis_dir / "image.nii.gz"
            mask_nifti_path = analysis_dir / "mask.nii.gz"

            if s3_utils.object_exists(image_nifti_key):
                if s3_utils.download_file(image_nifti_key, str(image_nifti_path)):
                    logger.info(f"Downloaded image NIfTI: {image_nifti_path}")
                else:
                    logger.warning(f"Failed to download image NIfTI: {image_nifti_key}")
            else:
                logger.warning(f"Image NIfTI not found: {image_nifti_key}")

            if s3_utils.object_exists(mask_nifti_key):
                if s3_utils.download_file(mask_nifti_key, str(mask_nifti_path)):
                    logger.info(f"Downloaded mask NIfTI: {mask_nifti_path}")
                else:
                    logger.warning(f"Failed to download mask NIfTI: {mask_nifti_key}")
            else:
                logger.warning(f"Mask NIfTI not found: {mask_nifti_key}")
            
            # List all files in analysis directory
            files_in_dir = list(analysis_dir.glob('*'))
            file_info = []
            for f in files_in_dir:
                if f.is_file():
                    size_mb = f.stat().st_size / (1024 * 1024)
                    file_info.append({
                        'name': f.name,
                        'path': str(f),
                        'size_bytes': f.stat().st_size,
                        'size_mb': round(size_mb, 2)
                    })
            
            logger.info(f"Analysis files ready in: {analysis_dir}")
            logger.info(f"Files: {[f['name'] for f in file_info]}")
            
            return Response({
                'study_id': str(study.id),
                'analysis_folder': str(analysis_dir),
                'files': file_info,
                'message': 'All analysis files are ready in the folder above. Download them for investigation.'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Failed to prepare analysis files: {e}", exc_info=True)
            return Response(
                {'error': f'Failed to prepare analysis files: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """
        Get signed URLs for visualization NIfTI files (image + segmentation mask).
        Frontend should overlay mask on top of the image.
        """
        study = self.get_object()
        
        # Check permission
        if request.user.clinic:
            allowed = study.clinic == request.user.clinic
        else:
            allowed = study.owner_id == request.user.id

        if not allowed:
            return Response(
                {'error': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Check if study is completed
            if study.status != 'COMPLETED':
                return Response(
                    {'error': 'Study not completed'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            s3_utils = S3Utils()
            owner_scope = study.get_owner_scope()
            default_image_key = f"results/{owner_scope}/{study.id}/image.nii.gz"
            default_mask_key = f"results/{owner_scope}/{study.id}/mask.nii.gz"
            image_s3_key = study.image_s3_key or default_image_key
            mask_s3_key = study.mask_s3_key or default_mask_key

            # Ensure files exist (generate if missing)
            if not (s3_utils.object_exists(image_s3_key) and s3_utils.object_exists(mask_s3_key)):
                logger.info("Visualization files missing; generating for study %s", study.id)
                self._create_result_file(study)

            if not s3_utils.object_exists(image_s3_key) or not s3_utils.object_exists(mask_s3_key):
                logger.warning("Visualization files not found: %s %s", image_s3_key, mask_s3_key)
                return Response(
                    {'error': 'Visualization files not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            image_url = s3_utils.generate_presigned_url(image_s3_key)
            mask_url = s3_utils.generate_presigned_url(mask_s3_key)
            logger.info("Generated signed URLs for visualization files: %s %s", image_s3_key, mask_s3_key)

            # Log audit
            AuditService.log_result_download(study, request.user)

            response_data = StudyResultSerializer({
                'study_id': str(study.id),
                'image_url': image_url,
                'mask_url': mask_url,
                'expires_in': 3600,
                'image_file_name': f"study_{study.id}_image.nii.gz",
                'mask_file_name': f"study_{study.id}_mask.nii.gz",
            }).data
            return Response(response_data)
        
        except Exception as e:
            logger.error(f"Failed to get result for study {study.id}: {e}", exc_info=True)
            payload = {'error': 'Failed to get result'}
            if settings.DEBUG:
                payload['detail'] = str(e)
            return Response(payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get'])
    def visualization(self, request, pk=None):
        """
        Alias for /result/ for frontend visualization.
        """
        return self.result(request, pk=pk)
    
    def _create_result_file(self, study):
        """
        Create visualization NIfTI files (image + 3D segmentation labelmap) when study is completed.
        Called automatically when status becomes COMPLETED.
        """
        temp_dir = None
        try:
            # Check if visualization files already exist
            s3_utils = S3Utils()
            owner_scope = study.get_owner_scope()
            default_image_key = f"results/{owner_scope}/{study.id}/image.nii.gz"
            default_mask_key = f"results/{owner_scope}/{study.id}/mask.nii.gz"
            image_s3_key = study.image_s3_key or default_image_key
            mask_s3_key = study.mask_s3_key or default_mask_key

            if s3_utils.object_exists(image_s3_key) and s3_utils.object_exists(mask_s3_key):
                # In dev mode we can validate local artifacts to avoid returning legacy 4D NIfTI files.
                should_regenerate = False
                if getattr(s3_utils, 'is_dev_mode', False):
                    try:
                        import nibabel as nib
                        image_local_path = str((s3_utils.storage_root / image_s3_key))
                        mask_local_path = str((s3_utils.storage_root / mask_s3_key))
                        image_img = nib.load(image_local_path)
                        mask_img = nib.load(mask_local_path)
                        if len(image_img.shape) != 3 or len(mask_img.shape) != 3:
                            logger.warning(
                                "Existing visualization files are not 3D (image=%s mask=%s); regenerating",
                                image_img.shape,
                                mask_img.shape,
                            )
                            should_regenerate = True
                    except Exception:
                        logger.warning("Failed to validate existing visualization files; regenerating", exc_info=True)
                        should_regenerate = True

                if not should_regenerate:
                    logger.info("Visualization files already exist for study %s", study.id)
                    if study.image_s3_key != image_s3_key or study.mask_s3_key != mask_s3_key:
                        study.image_s3_key = image_s3_key
                        study.mask_s3_key = mask_s3_key
                        study.save(update_fields=['image_s3_key', 'mask_s3_key', 'updated_at'])
                    return

                # Delete and regenerate (dev mode only)
                s3_utils.delete_object(image_s3_key)
                s3_utils.delete_object(mask_s3_key)
            
            logger.info("Creating visualization files for study %s", study.id)
            
            # Create temp directory
            temp_dir = tempfile.mkdtemp(prefix='results_')
            logger.info(f"Created temp directory: {temp_dir}")
            
            # Retrieve original image from storage
            original_npz_key_candidates = [
                f"uploads/{owner_scope}/{study.id}/file.npz",
                f"uploads/{owner_scope}/{study.id}/input.npz",  # legacy
            ]
            original_npz_key = next(
                (k for k in original_npz_key_candidates if s3_utils.object_exists(k)),
                original_npz_key_candidates[0],
            )
            original_npz_path = os.path.join(temp_dir, "file.npz")
            
            logger.info(f"Retrieving original image from storage: {original_npz_key}")
            if not s3_utils.download_file(original_npz_key, original_npz_path):
                raise FileNotFoundError(f"Original NPZ not found: {original_npz_key}")
            logger.info(f"Original image retrieved: {original_npz_path}")
            
            # Download mask from inference API
            mask_npz_path = os.path.join(temp_dir, "mask.npz")
            logger.info(f"Downloading mask from inference API to: {mask_npz_path}")
            
            inference_client = InferenceClient()
            if not inference_client.get_results(study.inference_job_id, mask_npz_path):
                raise Exception("Failed to download mask from inference API")
            logger.info(f"Mask downloaded successfully: {mask_npz_path}")
            
            # Convert image NPZ -> NIfTI image
            image_nifti_path = os.path.join(temp_dir, "image.nii.gz")
            logger.info("Converting image NPZ to NIfTI: %s", image_nifti_path)
            if not NiftiConverter.npz_to_nifti(original_npz_path, image_nifti_path):
                raise Exception("Failed to convert image NPZ to NIfTI")
            if not os.path.exists(image_nifti_path):
                raise FileNotFoundError(f"Image NIfTI file not created: {image_nifti_path}")

            # Convert mask NPZ -> NIfTI labelmap (mask-only conversion; no joining)
            mask_nifti_path = os.path.join(temp_dir, "mask.nii.gz")
            logger.info("Converting mask NPZ to NIfTI: %s", mask_nifti_path)
            mask_spacing = None
            try:
                with np.load(original_npz_path, allow_pickle=True) as img_data:
                    if 'spacing' in img_data.files:
                        mask_spacing = img_data['spacing']
            except Exception:
                logger.warning("Could not read spacing from original NPZ; using defaults", exc_info=True)

            if not NiftiConverter.segs_npz_to_nifti(mask_npz_path, mask_nifti_path, spacing=mask_spacing):
                raise Exception("Failed to convert mask NPZ to NIfTI")
            if not os.path.exists(mask_nifti_path):
                raise FileNotFoundError(f"Mask NIfTI file not created: {mask_nifti_path}")

            # Upload to storage (S3 in prod, local in dev)
            logger.info("Uploading visualization files to storage: %s %s", image_s3_key, mask_s3_key)
            if not s3_utils.upload_file(image_nifti_path, image_s3_key, 'application/gzip'):
                raise Exception(f"Failed to upload file to storage: {image_s3_key}")
            if not s3_utils.upload_file(mask_nifti_path, mask_s3_key, 'application/gzip'):
                raise Exception(f"Failed to upload file to storage: {mask_s3_key}")

            # Update study
            study.image_s3_key = image_s3_key
            study.mask_s3_key = mask_s3_key
            study.save(update_fields=['image_s3_key', 'mask_s3_key', 'updated_at'])
            logger.info("Study updated with visualization keys")

            # Persist analysis artifacts (original NPZ, mask NPZ, final NIfTI) locally
            if getattr(settings, 'SAVE_ANALYSIS_ARTIFACTS', False):
                analysis_dir = self._get_analysis_dir(study_id=str(study.id))
                analysis_dir.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(original_npz_path, analysis_dir / "file.npz")
                    shutil.copy2(mask_npz_path, analysis_dir / "mask.npz")
                    shutil.copy2(image_nifti_path, analysis_dir / "image.nii.gz")
                    shutil.copy2(mask_nifti_path, analysis_dir / "mask.nii.gz")
                    logger.info(f"Saved analysis artifacts to: {analysis_dir}")
                except Exception:
                    logger.warning("Failed to save analysis artifacts", exc_info=True)
            
        except Exception as e:
            logger.error(f"Failed to create visualization files for study {study.id}: {e}", exc_info=True)
            # Don't raise exception - let status endpoint still return COMPLETED
            # User can retry by calling /result/ endpoint
        
        finally:
            # Cleanup temp files
            if temp_dir and os.path.exists(temp_dir):
                logger.info(f"Cleaning up temp directory: {temp_dir}")
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _resolve_category_and_prompt(category_id: str) -> tuple[str, str]:
        """
        Resolve a category selection into a stored category name and a prompt text.

        Supports `data/categories.json` being either:
        - a single object dict, or
        - a list of category dicts.
        """
        categories_path = settings.BASE_DIR / 'data' / 'categories.json'

        categories: list[dict] = []
        try:
            with open(categories_path, 'r') as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                categories = loaded
            elif isinstance(loaded, dict):
                categories = [loaded]
        except Exception as e:
            logger.warning(f"Failed to load categories from {categories_path}: {e}")

        selected: dict | None = None
        category_id_normalized = str(category_id or '').strip()

        if category_id_normalized:
            for cat in categories:
                cat_id = cat.get('id')
                cat_name = cat.get('name')
                if cat_id is not None and str(cat_id) == category_id_normalized:
                    selected = cat
                    break
                if cat_name and str(cat_name).strip().lower() == category_id_normalized.lower():
                    selected = cat
                    break

        if selected is None and categories:
            selected = categories[0]

        category_name = (selected or {}).get('name') or (category_id_normalized or 'Unknown')
        prompt_text = (selected or {}).get('prompt') or f"segment {category_name}"
        return category_name, prompt_text

    @staticmethod
    def _get_analysis_dir(study_id: str | None) -> Path:
        root = Path(getattr(settings, 'ANALYSIS_ROOT_DIR', '/tmp/vizier-analysis'))
        return root / (study_id or "_pending")

    @staticmethod
    def _ensure_npz_text_prompts(npz_path: str, text_prompts: dict) -> None:
        """
        Ensure the NPZ contains a `text_prompts` key compatible with the inference API.

        If the key is missing, the file is rewritten in-place (atomic replace).
        """
        try:
            with np.load(npz_path, allow_pickle=True) as data:
                if 'text_prompts' in data.files:
                    logger.info("NPZ already contains text_prompts; leaving as is")
                    return

                payload = {k: data[k] for k in data.files}

            payload['text_prompts'] = np.array(text_prompts, dtype=object)

            tmp_dir = os.path.dirname(npz_path)
            tmp_file = tempfile.NamedTemporaryFile(dir=tmp_dir, suffix='.npz', delete=False)
            tmp_path = tmp_file.name
            tmp_file.close()

            np.savez_compressed(tmp_path, **payload)
            os.replace(tmp_path, npz_path)
            logger.info("Added text_prompts to NPZ: %s", npz_path)

        except Exception:
            logger.warning("Failed to ensure text_prompts in NPZ", exc_info=True)
