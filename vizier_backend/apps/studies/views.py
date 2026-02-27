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
from rest_framework.exceptions import ValidationError
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

        # Resolve category (name + prompt) before heavy file processing.
        # Return field-specific errors for easier API testing/debugging.
        category_id = serializer.validated_data['category_id']
        exam_modality = serializer.validated_data['exam_modality']
        try:
            category_name, text_prompts, normalized_modality = self._resolve_category_and_prompt(
                category_id=category_id,
                exam_modality=exam_modality,
            )
        except ValueError as exc:
            raise ValidationError(self._map_upload_metadata_error(str(exc)))
        
        temp_dir = None
        study = None
        try:
            upload_file = serializer.validated_data.get('upload_file')
            upload_type = serializer.validated_data.get('upload_type')

            # Create temp directory for processing
            temp_dir = tempfile.mkdtemp(prefix='dicom_')
            logger.info(f"Created temp directory: {temp_dir}")

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
                    exam_modality=normalized_modality,
                    category_hint=category_id,
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

                # Normalize uploaded NPZ to the same target shape policy used in ZIP uploads.
                dicom_service = DicomZipToNpzService()
                npz_path = dicom_service.preprocess_existing_npz(
                    npz_path=npz_path,
                    exam_modality=normalized_modality,
                    category_hint=category_id,
                )

                # Keep inference prompts aligned with the selected modality/category.
                self._ensure_npz_text_prompts(
                    npz_path=npz_path,
                    text_prompts=text_prompts,
                    overwrite=True,
                )

            elif upload_type == 'nifti':
                nifti_filename = os.path.basename(getattr(upload_file, 'name', 'input.nii.gz') or 'input.nii.gz')
                nifti_path = os.path.join(temp_dir, nifti_filename)
                with open(nifti_path, 'wb') as f:
                    for chunk in upload_file.chunks():
                        f.write(chunk)
                logger.info(f"Saved uploaded NIfTI: {nifti_path}")

                dicom_service = DicomZipToNpzService()
                npz_path = dicom_service.convert_nifti_to_npz(
                    nifti_path=nifti_path,
                    text_prompts=text_prompts,
                    output_npz_path=npz_path,
                    exam_modality=normalized_modality,
                    category_hint=category_id,
                )
                logger.info(f"Converted NIfTI to NPZ: {npz_path} ({os.path.getsize(npz_path)} bytes)")

            else:
                raise ValueError(f"Unsupported upload_type: {upload_type}")
            
            # Create Study record
            try:
                study = Study.objects.create(
                    clinic=request.user.clinic if request.user.clinic else None,
                    owner=request.user,
                    category=category_name,
                    case_identification=serializer.validated_data['case_identification'],
                    patient_name=serializer.validated_data['patient_name'],
                    age=serializer.validated_data['age'],
                    exam_source=serializer.validated_data['exam_source'],
                    exam_modality=normalized_modality,
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

            segments_legend = []
            try:
                segments_legend = self._build_segments_legend_for_study(study=study, s3_utils=s3_utils)
            except Exception:
                logger.warning("Failed to build segmentation legend for study %s", study.id, exc_info=True)

            # Log audit
            AuditService.log_result_download(study, request.user)

            response_data = StudyResultSerializer({
                'study_id': str(study.id),
                'image_url': image_url,
                'mask_url': mask_url,
                'segments_legend': segments_legend,
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
            default_mask_npz_key = f"results/{owner_scope}/{study.id}/mask.npz"
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
            if not s3_utils.upload_file(mask_npz_path, default_mask_npz_key, 'application/octet-stream'):
                logger.warning("Failed to upload mask NPZ to storage: %s", default_mask_npz_key)

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
    def _map_upload_metadata_error(message: str) -> dict:
        """Map catalog validation errors to field-level API errors."""
        normalized = str(message or '').strip()
        if normalized.startswith("Invalid exam_modality:") or normalized == "exam_modality is required":
            return {"exam_modality": [normalized]}
        if normalized.startswith("Invalid category_id:") or normalized == "category_id is required":
            return {"category_id": [normalized]}
        if normalized in {
            "Selected target does not belong to exam_modality",
            "Selected category does not belong to exam_modality",
        }:
            return {
                "category_id": [normalized],
                "exam_modality": ["Selected modality does not match target/category"],
            }
        return {"non_field_errors": [normalized or "Invalid metadata"]}

    @staticmethod
    def _resolve_category_and_prompt(category_id: str, exam_modality: str) -> tuple[str, dict, str]:
        """
        Resolve category-group and modality into canonical category name + prompts.

        Returns:
            (category_display_name, text_prompts, normalized_modality_name)

        Raises:
            ValueError: When modality/category is invalid or mismatched.
        """
        categories_path = settings.BASE_DIR / 'data' / 'categories.json'
        if not str(exam_modality or '').strip():
            raise ValueError("exam_modality is required")
        if not str(category_id or '').strip():
            raise ValueError("category_id is required")

        try:
            with open(categories_path, 'r') as f:
                loaded = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load categories from {categories_path}: {e}")
            raise ValueError("Failed to load categories catalog") from e

        raw_modalities = None
        if isinstance(loaded, dict) and isinstance(loaded.get('modalities'), dict):
            raw_modalities = loaded.get('modalities')
        elif isinstance(loaded, dict) and isinstance(loaded.get('modalities'), list):
            raw_modalities = {}
            for item in loaded.get('modalities', []):
                if not isinstance(item, dict):
                    continue
                modality_name = str(item.get('name') or item.get('id') or '').strip()
                if not modality_name:
                    continue
                raw_modalities[modality_name] = {
                    'default': item.get('targets') or [],
                }
        elif isinstance(loaded, dict):
            raw_modalities = {k: v for k, v in loaded.items() if isinstance(v, dict)}

        if not raw_modalities:
            raise ValueError("Failed to load categories catalog")

        modalities: list[dict] = []
        for modality_key, modality_value in raw_modalities.items():
            modality_display = str(modality_key).strip()
            modality_aliases = {modality_display}
            groups_payload = None

            if isinstance(modality_value, dict) and any(
                field in modality_value for field in ['groups', 'categories', 'regions']
            ):
                modality_display = str(modality_value.get('name') or modality_display).strip() or modality_display
                modality_id = str(modality_value.get('id') or '').strip()
                if modality_id:
                    modality_aliases.add(modality_id)
                groups_payload = (
                    modality_value.get('groups')
                    or modality_value.get('categories')
                    or modality_value.get('regions')
                    or {}
                )
            elif isinstance(modality_value, dict):
                groups_payload = modality_value

            if not isinstance(groups_payload, dict):
                continue

            groups: list[dict] = []
            for group_key, group_value in groups_payload.items():
                group_key_text = str(group_key).strip()
                group_display = group_key_text
                targets = group_value
                if isinstance(group_value, dict):
                    group_display = str(group_value.get('name') or group_display).strip() or group_display
                    targets = group_value.get('targets') or []
                if not group_key_text or not isinstance(targets, list):
                    continue
                groups.append(
                    {
                        'key': group_key_text,
                        'name': group_display,
                        'targets': targets,
                    }
                )

            if groups:
                modalities.append(
                    {
                        'name': modality_display,
                        'aliases': modality_aliases,
                        'groups': groups,
                    }
                )

        if not modalities:
            raise ValueError("Failed to load categories catalog")

        modality_query = StudyViewSet._normalize_catalog_token(exam_modality)
        category_query = StudyViewSet._normalize_catalog_token(category_id)

        selected_modality = None
        for modality in modalities:
            candidates = {
                StudyViewSet._normalize_catalog_token(modality.get('name')),
                *(StudyViewSet._normalize_catalog_token(alias) for alias in modality.get('aliases', set())),
            }
            candidates.discard('')
            if modality_query in candidates:
                selected_modality = modality
                break

        if selected_modality is None:
            available_modalities = ", ".join(sorted(str(m.get('name')) for m in modalities))
            raise ValueError(f"Invalid exam_modality: {exam_modality}. Available: {available_modalities}")

        modality_name = str(selected_modality.get('name') or exam_modality).strip()
        modality_token = StudyViewSet._normalize_catalog_token(modality_name)
        selected_group = None

        for group in selected_modality.get('groups', []):
            group_key = str(group.get('key') or '').strip()
            group_name = str(group.get('name') or group_key).strip() or group_key
            group_tokens = {
                StudyViewSet._normalize_catalog_token(group_key),
                StudyViewSet._normalize_catalog_token(group_name),
                f"{modality_token}{StudyViewSet._normalize_catalog_token(group_key)}",
                f"{modality_token}{StudyViewSet._normalize_catalog_token(group_name)}",
            }
            group_tokens.discard('')
            if category_query in group_tokens:
                selected_group = group
                break

        # Backward compatibility: category_id may still come as a target name/id.
        if selected_group is None:
            for group in selected_modality.get('groups', []):
                for target_item in group.get('targets', []):
                    target_name, _ = StudyViewSet._extract_target_name_and_prompt(
                        target_item=target_item,
                        modality_name=modality_name,
                        category_name=str(group.get('name') or group.get('key') or '').strip(),
                    )
                    if not target_name:
                        continue
                    target_token = StudyViewSet._normalize_catalog_token(target_name)
                    target_tokens = {
                        target_token,
                        f"{modality_token}{target_token}",
                    }
                    target_tokens.discard('')
                    if category_query in target_tokens:
                        selected_group = group
                        break
                if selected_group is not None:
                    break

        if selected_group is None:
            for other_modality in modalities:
                other_name = str(other_modality.get('name') or '').strip()
                other_token = StudyViewSet._normalize_catalog_token(other_name)
                if other_token == modality_token:
                    continue
                for group in other_modality.get('groups', []):
                    group_key = str(group.get('key') or '').strip()
                    group_name = str(group.get('name') or group_key).strip()
                    group_tokens = {
                        StudyViewSet._normalize_catalog_token(group_key),
                        StudyViewSet._normalize_catalog_token(group_name),
                        f"{other_token}{StudyViewSet._normalize_catalog_token(group_key)}",
                        f"{other_token}{StudyViewSet._normalize_catalog_token(group_name)}",
                    }
                    group_tokens.discard('')
                    if category_query in group_tokens:
                        raise ValueError("Selected category does not belong to exam_modality")

            available_groups = ", ".join(
                sorted(str(group.get('name') or group.get('key') or '').strip() for group in selected_modality.get('groups', []))
            )
            raise ValueError(
                f"Invalid category_id: {category_id}. Available categories for {modality_name}: {available_groups}"
            )

        group_name = str(selected_group.get('name') or selected_group.get('key') or category_id).strip()
        category_display = f"{modality_name}: {group_name}"

        text_prompts = {}
        prompt_index = 1
        for target_item in selected_group.get('targets', []):
            _, prompt_text = StudyViewSet._extract_target_name_and_prompt(
                target_item=target_item,
                modality_name=modality_name,
                category_name=group_name,
            )
            if not prompt_text:
                continue
            text_prompts[str(prompt_index)] = prompt_text
            prompt_index += 1

        if prompt_index == 1:
            raise ValueError(f"Invalid category_id: {category_id}. Selected category has no targets")

        text_prompts['instance_label'] = 0
        return category_display, text_prompts, modality_name

    @staticmethod
    def _extract_target_name_and_prompt(target_item, modality_name: str, category_name: str) -> tuple[str, str]:
        """Extract target name/prompt from catalog item (str or dict)."""
        target_name = ''
        prompt_text = ''
        if isinstance(target_item, dict):
            target_name = str(target_item.get('name') or target_item.get('label') or '').strip()
            prompt_text = str(target_item.get('prompt') or '').strip()
        else:
            target_name = str(target_item or '').strip()

        if not target_name:
            return '', ''
        if not prompt_text:
            prompt_text = StudyViewSet._build_default_prompt(
                modality_name=modality_name,
                category_name=category_name,
                target_name=target_name,
            )
        return target_name, prompt_text

    @staticmethod
    def _build_default_prompt(modality_name: str, category_name: str, target_name: str) -> str:
        """Build default text prompt when not explicitly provided in catalog."""
        modality_token = StudyViewSet._normalize_catalog_token(modality_name)
        modality_label = 'MR' if modality_token == 'mri' else modality_name
        return f"Visualization of {target_name} in {category_name} {modality_label}"

    @staticmethod
    def _normalize_catalog_token(value) -> str:
        """Lowercase/alphanumeric token for flexible catalog matching."""
        raw = str(value or '').strip().lower()
        return ''.join(ch for ch in raw if ch.isalnum())

    @staticmethod
    def _extract_label_from_prompt(prompt_text: str) -> str:
        """Extract a concise label from an inference prompt sentence."""
        text = str(prompt_text or '').strip()
        if not text:
            return ''

        lowered = text.lower()
        for prefix in ('visualization of ', 'segmentation of '):
            if lowered.startswith(prefix):
                in_idx = lowered.find(' in ')
                if in_idx > len(prefix):
                    return text[len(prefix):in_idx].strip()
        return text

    @staticmethod
    def _legend_color_for_label(label_id: int) -> str:
        """Deterministic color assignment per label id."""
        palette = [
            '#e11d48', '#2563eb', '#059669', '#f59e0b', '#7c3aed',
            '#db2777', '#0891b2', '#16a34a', '#dc2626', '#8b5cf6',
            '#0ea5e9', '#84cc16',
        ]
        index = int(label_id) % len(palette)
        return palette[index]

    @staticmethod
    def _parse_text_prompts(raw_prompts) -> tuple[dict, int]:
        """
        Parse NPZ text_prompts payload into a dict and instance/background label.
        """
        payload = raw_prompts
        if isinstance(payload, np.ndarray):
            if payload.shape == ():
                payload = payload.item()
            elif payload.size == 1:
                payload = payload.reshape(()).item()

        if not isinstance(payload, dict):
            return {}, 0

        prompt_map = {}
        for key, value in payload.items():
            key_text = str(key).strip()
            if key_text == 'instance_label':
                continue
            prompt_map[key_text] = str(value).strip()

        instance_label_raw = payload.get('instance_label', 0)
        try:
            instance_label = int(instance_label_raw)
        except Exception:
            instance_label = 0
        return prompt_map, instance_label

    @staticmethod
    def _build_segments_legend_from_arrays(segs: np.ndarray, text_prompts: dict, instance_label: int = 0) -> list[dict]:
        """
        Build frontend legend data by cross-referencing seg IDs with text prompts.
        """
        if segs is None:
            return []
        segs = np.asarray(segs)
        if segs.size == 0:
            return []

        if segs.dtype.kind not in ('i', 'u'):
            segs = np.nan_to_num(segs, nan=float(instance_label), posinf=float(instance_label), neginf=float(instance_label))
            segs = np.rint(segs).astype(np.int32, copy=False)

        unique_vals, counts = np.unique(segs, return_counts=True)
        total_voxels = int(segs.size)
        legend = []

        for val, count in zip(unique_vals, counts):
            label_id = int(val)
            if label_id == int(instance_label):
                continue

            prompt = str(text_prompts.get(str(label_id)) or '').strip()
            label = StudyViewSet._extract_label_from_prompt(prompt) or f"Label {label_id}"
            fraction = float(count) / float(total_voxels) if total_voxels else 0.0

            legend.append(
                {
                    'id': label_id,
                    'label': label,
                    'prompt': prompt,
                    'voxels': int(count),
                    'fraction': fraction,
                    'percentage': round(fraction * 100.0, 4),
                    'color': StudyViewSet._legend_color_for_label(label_id),
                }
            )

        legend.sort(key=lambda item: item['voxels'], reverse=True)
        return legend

    def _build_segments_legend_for_study(self, study, s3_utils: S3Utils) -> list[dict]:
        """
        Build legend for a study by reading original prompts and mask labels.
        """
        owner_scope = study.get_owner_scope()
        original_npz_key_candidates = [
            f"uploads/{owner_scope}/{study.id}/file.npz",
            f"uploads/{owner_scope}/{study.id}/input.npz",
        ]
        original_npz_key = next(
            (k for k in original_npz_key_candidates if s3_utils.object_exists(k)),
            original_npz_key_candidates[0],
        )
        mask_npz_key = f"results/{owner_scope}/{study.id}/mask.npz"

        temp_dir = tempfile.mkdtemp(prefix='legend_')
        try:
            original_npz_path = os.path.join(temp_dir, 'file.npz')
            mask_npz_path = os.path.join(temp_dir, 'mask.npz')

            if not s3_utils.download_file(original_npz_key, original_npz_path):
                logger.warning("Cannot build legend: missing original NPZ key %s", original_npz_key)
                return []

            if not s3_utils.download_file(mask_npz_key, mask_npz_path):
                job_id = study.inference_job_id or getattr(study.job, 'external_job_id', None)
                if not job_id:
                    logger.warning("Cannot build legend: missing mask NPZ and job id for study %s", study.id)
                    return []
                inference_client = InferenceClient()
                if not inference_client.get_results(job_id, mask_npz_path):
                    logger.warning("Cannot build legend: failed to fetch mask NPZ for job %s", job_id)
                    return []
                s3_utils.upload_file(mask_npz_path, mask_npz_key, 'application/octet-stream')

            with np.load(original_npz_path, allow_pickle=True) as image_npz:
                raw_prompts = image_npz['text_prompts'] if 'text_prompts' in image_npz.files else {}
            prompt_map, instance_label = self._parse_text_prompts(raw_prompts)

            with np.load(mask_npz_path, allow_pickle=False) as mask_npz:
                segs = None
                for key in ('segs', 'mask', 'result', 'imgs'):
                    if key in mask_npz.files:
                        segs = mask_npz[key]
                        break
                if segs is None:
                    logger.warning("Cannot build legend: mask NPZ has no segmentation key")
                    return []

            return self._build_segments_legend_from_arrays(
                segs=segs,
                text_prompts=prompt_map,
                instance_label=instance_label,
            )
        finally:
            cleanup_temp_files(temp_dir)

    @staticmethod
    def _get_analysis_dir(study_id: str | None) -> Path:
        root = Path(getattr(settings, 'ANALYSIS_ROOT_DIR', '/tmp/vizier-analysis'))
        return root / (study_id or "_pending")

    @staticmethod
    def _ensure_npz_text_prompts(npz_path: str, text_prompts: dict, overwrite: bool = False) -> None:
        """
        Ensure the NPZ contains a `text_prompts` key compatible with the inference API.

        If overwrite is False, only adds text_prompts when missing.
        If overwrite is True, always replaces existing prompts.
        """
        try:
            has_prompts = False
            with np.load(npz_path, allow_pickle=True) as data:
                has_prompts = 'text_prompts' in data.files
                if has_prompts and not overwrite:
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
            if has_prompts and overwrite:
                logger.info("Replaced text_prompts in NPZ: %s", npz_path)
            else:
                logger.info("Added text_prompts to NPZ: %s", npz_path)

        except Exception:
            logger.warning("Failed to ensure text_prompts in NPZ", exc_info=True)
