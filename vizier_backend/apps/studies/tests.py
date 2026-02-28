from django.test import TestCase, RequestFactory
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
import os
import tempfile
import numpy as np
import json
from pathlib import Path
import nibabel as nib
from unittest.mock import patch
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.accounts.permissions import TenantQuerySetMixin
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.studies.models import Study
from apps.studies.serializers import StudyCreateSerializer
from apps.tenants.models import Clinic
from apps.studies.views import StudyViewSet
from services.dicom_pipeline import DicomZipToNpzService


class _BaseQueryView:
    queryset = Study.objects.all()

    def get_queryset(self):
        return self.queryset


class _TenantStudyQueryView(TenantQuerySetMixin, _BaseQueryView):
    pass


class StudyOwnershipModelTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        self.individual = User.objects.create_user(
            email='individual@example.com',
            cognito_sub='individual-sub',
            role='INDIVIDUAL',
        )

        self.clinic_owner = User.objects.create_user(
            email='owner@example.com',
            cognito_sub='owner-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Test Clinic',
            cnpj='12345678000199',
            owner=self.clinic_owner,
        )
        self.clinic_owner.clinic = self.clinic
        self.clinic_owner.save(update_fields=['clinic'])

    def test_individual_can_create_study_without_clinic(self):
        study = Study.objects.create(
            clinic=None,
            owner=self.individual,
            category='test-category',
            status='SUBMITTED',
        )

        self.assertIsNone(study.clinic)
        self.assertEqual(study.owner, self.individual)
        self.assertEqual(study.get_owner_scope(), f"individual/{self.individual.id}")

    def test_clinic_study_owner_scope_is_clinic_id(self):
        study = Study.objects.create(
            clinic=self.clinic,
            owner=self.clinic_owner,
            category='clinic-study',
            status='SUBMITTED',
        )

        self.assertEqual(study.get_owner_scope(), str(self.clinic.id))

    def test_tenant_mixin_filters_individual_by_owner(self):
        mine = Study.objects.create(
            clinic=None,
            owner=self.individual,
            category='mine',
            status='SUBMITTED',
        )
        other_user = User.objects.create_user(
            email='other@example.com',
            cognito_sub='other-sub',
            role='INDIVIDUAL',
        )
        Study.objects.create(
            clinic=None,
            owner=other_user,
            category='other',
            status='SUBMITTED',
        )

        view = _TenantStudyQueryView()
        request = self.factory.get('/api/studies/')
        request.user = self.individual
        view.request = request

        queryset = view.get_queryset()

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first(), mine)

    def test_tenant_mixin_filters_clinic_user_by_clinic(self):
        clinic_study = Study.objects.create(
            clinic=self.clinic,
            owner=self.clinic_owner,
            category='clinic',
            status='SUBMITTED',
        )
        Study.objects.create(
            clinic=None,
            owner=self.individual,
            category='personal',
            status='SUBMITTED',
        )

        view = _TenantStudyQueryView()
        request = self.factory.get('/api/studies/')
        request.user = self.clinic_owner
        view.request = request

        queryset = view.get_queryset()

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first(), clinic_study)

    def test_audit_skips_study_events_without_clinic(self):
        study = Study.objects.create(
            clinic=None,
            owner=self.individual,
            category='mine',
            status='SUBMITTED',
        )

        AuditService.log_study_submit(study)
        AuditService.log_study_status_check(study)
        AuditService.log_result_download(study, self.individual)

        self.assertEqual(AuditLog.objects.count(), 0)

    def test_audit_logs_study_submit_for_clinic_study(self):
        study = Study.objects.create(
            clinic=self.clinic,
            owner=self.clinic_owner,
            category='clinic',
            status='SUBMITTED',
        )

        AuditService.log_study_submit(study)

        self.assertEqual(AuditLog.objects.count(), 1)
        audit_log = AuditLog.objects.first()
        self.assertEqual(audit_log.clinic, self.clinic)
        self.assertEqual(audit_log.action, 'STUDY_SUBMIT')
        self.assertEqual(audit_log.resource_id, str(study.id))


class NpzPreprocessingServiceTest(TestCase):
    @override_settings(DICOM_TARGET_HW=(64, 64), DICOM_TARGET_SLICES=32)
    def test_preprocess_existing_npz_resizes_and_preserves_slices(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            npz_path = os.path.join(tmpdir, 'file.npz')
            volume = np.random.rand(120, 321, 321).astype(np.float32)

            np.savez_compressed(
                npz_path,
                image=volume,
                spacing=np.array((1.0, 1.0, 1.0), dtype=np.float32),
                text_prompts=np.array({'1': 'segment brain', 'instance_label': 0}, dtype=object),
            )

            service = DicomZipToNpzService()
            service.preprocess_existing_npz(npz_path=npz_path)

            with np.load(npz_path, allow_pickle=True) as data:
                self.assertEqual(set(data.files), {'imgs', 'spacing', 'text_prompts'})
                self.assertEqual(tuple(data['imgs'].shape), (120, 64, 64))
                self.assertEqual(data['imgs'].dtype, np.float16)


class NpzPromptOverwriteTest(TestCase):
    def test_overwrite_text_prompts_when_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            npz_path = os.path.join(tmpdir, 'file.npz')
            np.savez_compressed(
                npz_path,
                imgs=np.zeros((4, 4, 4), dtype=np.float16),
                text_prompts=np.array({'1': 'old prompt', 'instance_label': 0}, dtype=object),
            )

            StudyViewSet._ensure_npz_text_prompts(
                npz_path=npz_path,
                text_prompts={'1': 'new prompt', '2': 'second prompt', 'instance_label': 0},
                overwrite=True,
            )

            with np.load(npz_path, allow_pickle=True) as data:
                prompts = data['text_prompts'].item()
                self.assertEqual(prompts['1'], 'new prompt')
                self.assertEqual(prompts['2'], 'second prompt')
                self.assertEqual(prompts['instance_label'], 0)


class SegmentationLegendTest(TestCase):
    def test_build_segments_legend_cross_references_prompt_ids(self):
        segs = np.array(
            [
                [0, 1, 1, 2],
                [0, 2, 2, 0],
            ],
            dtype=np.uint8,
        )
        text_prompts = {
            '1': 'Visualization of brain tumor in head MR',
            '2': 'Visualization of stroke lesion in head MR',
        }

        legend = StudyViewSet._build_segments_legend_from_arrays(
            segs=segs,
            text_prompts=text_prompts,
            instance_label=0,
        )

        self.assertEqual(len(legend), 2)
        self.assertEqual(legend[0]['id'], 2)
        self.assertEqual(legend[0]['label'], 'stroke lesion')
        self.assertEqual(legend[0]['voxels'], 3)
        self.assertEqual(legend[1]['id'], 1)
        self.assertEqual(legend[1]['label'], 'brain tumor')
        self.assertEqual(legend[1]['voxels'], 2)

    def test_parse_text_prompts_extracts_instance_label(self):
        raw = np.array(
            {
                '1': 'Visualization of lesion A in head MR',
                '2': 'Visualization of lesion B in head MR',
                'instance_label': 9,
            },
            dtype=object,
        )

        prompt_map, instance_label = StudyViewSet._parse_text_prompts(raw)

        self.assertEqual(instance_label, 9)
        self.assertEqual(prompt_map['1'], 'Visualization of lesion A in head MR')
        self.assertEqual(prompt_map['2'], 'Visualization of lesion B in head MR')

    def test_extract_label_from_prompt_fallback(self):
        label = StudyViewSet._extract_label_from_prompt('Custom Label Format')
        self.assertEqual(label, 'Custom Label Format')

    def test_convert_mask_npz_to_reference_nifti_preserves_reference_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_path = os.path.join(tmpdir, 'reference.nii.gz')
            mask_npz_path = os.path.join(tmpdir, 'mask.npz')
            out_mask_path = os.path.join(tmpdir, 'mask_resampled.nii.gz')

            reference = np.random.rand(20, 64, 64).astype(np.float32)
            nib.save(nib.Nifti1Image(reference, np.eye(4)), reference_path)

            segs_small = np.zeros((10, 32, 32), dtype=np.uint8)
            segs_small[2:8, 8:20, 8:24] = 3
            np.savez(mask_npz_path, segs=segs_small)

            ok = StudyViewSet._convert_mask_npz_to_reference_nifti(
                mask_npz_path=mask_npz_path,
                reference_nifti_path=reference_path,
                output_nifti_path=out_mask_path,
            )

            self.assertTrue(ok)
            out_img = nib.load(out_mask_path)
            self.assertEqual(tuple(out_img.shape), (20, 64, 64))
            out_data = np.asanyarray(out_img.dataobj)
            self.assertIn(3, np.unique(out_data))


class IntensityNormalizationServiceTest(TestCase):
    def test_ct_lung_window_rescales_to_0_255(self):
        service = DicomZipToNpzService()
        volume = np.array([[-1200.0, -160.0, 700.0]], dtype=np.float32)

        normalized = service._normalize_intensity(
            volume=volume,
            exam_modality='CT',
            category_hint='ct_lung_lesions',
        )

        self.assertAlmostEqual(float(normalized.min()), 0.0, places=3)
        self.assertAlmostEqual(float(normalized.max()), 255.0, places=3)
        self.assertAlmostEqual(float(normalized[0, 1]), 127.5, places=1)

    def test_non_ct_uses_percentiles_and_rescales(self):
        service = DicomZipToNpzService()
        volume = np.array([[0.0, 10.0, 20.0, 30.0, 10000.0]], dtype=np.float32)

        normalized = service._normalize_intensity(
            volume=volume,
            exam_modality='MRI',
            category_hint='mri_glioma',
        )

        self.assertGreaterEqual(float(normalized.min()), 0.0)
        self.assertLessEqual(float(normalized.max()), 255.0)
        self.assertAlmostEqual(float(normalized.max()), 255.0, places=3)

    def test_skip_when_already_in_0_255(self):
        service = DicomZipToNpzService()
        volume = np.array([[0.0, 64.0, 128.0, 255.0]], dtype=np.float32)

        normalized = service._normalize_intensity(
            volume=volume,
            exam_modality='PET',
            category_hint='pet_whole_body_lesion',
        )

        np.testing.assert_allclose(normalized, volume, rtol=1e-6, atol=1e-6)


class CategoryResolutionTest(TestCase):
    def test_resolve_category_group_to_multi_prompt_payload(self):
        catalog = {
            "CT": {
                "abdomen": ["liver tumors"]
            },
            "MRI": {
                "head": [
                    "non-enhancing tumor core",
                    "enhancing tissue",
                ],
                "GU": [
                    "prostate lesion",
                ],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            data_dir = base_dir / 'data'
            data_dir.mkdir(parents=True, exist_ok=True)
            with open(data_dir / 'categories.json', 'w') as f:
                json.dump(catalog, f)

            with override_settings(BASE_DIR=base_dir):
                category_name, prompts, modality = StudyViewSet._resolve_category_and_prompt('head', 'mri')

        self.assertEqual(category_name, 'MRI: head')
        self.assertEqual(modality, 'MRI')
        self.assertEqual(prompts['instance_label'], 0)
        self.assertEqual(prompts['1'], 'Visualization of non-enhancing tumor core in head MR')
        self.assertEqual(prompts['2'], 'Visualization of enhancing tissue in head MR')

    def test_resolve_category_raises_when_group_not_in_modality(self):
        catalog = {
            "CT": {
                "abdomen": ["liver tumors"],
            },
            "MRI": {
                "head": ["brain tumor"],
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            data_dir = base_dir / 'data'
            data_dir.mkdir(parents=True, exist_ok=True)
            with open(data_dir / 'categories.json', 'w') as f:
                json.dump(catalog, f)

            with override_settings(BASE_DIR=base_dir):
                with self.assertRaises(ValueError):
                    StudyViewSet._resolve_category_and_prompt('abdomen', 'mri')


class NiftiConversionServiceTest(TestCase):
    @override_settings(DICOM_TARGET_HW=(64, 64), DICOM_TARGET_SLICES=32)
    def test_convert_nifti_to_npz_resizes_and_preserves_slices(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nifti_path = os.path.join(tmpdir, 'input.nii.gz')
            npz_path = os.path.join(tmpdir, 'file.npz')

            volume_xyz = np.random.rand(90, 80, 40).astype(np.float32)
            nii = nib.Nifti1Image(volume_xyz, affine=np.eye(4))
            nii.header.set_zooms((1.0, 1.2, 2.5))
            nib.save(nii, nifti_path)

            service = DicomZipToNpzService()
            service.convert_nifti_to_npz(
                nifti_path=nifti_path,
                text_prompts={"1": "Visualization of glioma in MRI", "instance_label": 0},
                output_npz_path=npz_path,
            )

            with np.load(npz_path, allow_pickle=True) as data:
                self.assertEqual(set(data.files), {'imgs', 'spacing', 'text_prompts'})
                self.assertEqual(tuple(data['imgs'].shape), (40, 64, 64))
                self.assertEqual(data['imgs'].dtype, np.float16)
                np.testing.assert_allclose(data['spacing'], np.array([2.5, 1.2, 1.0]), rtol=1e-6)

    def test_convert_npz_to_nifti_keeps_original_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            npz_path = os.path.join(tmpdir, 'input.npz')
            nifti_path = os.path.join(tmpdir, 'original.nii.gz')

            volume = np.random.rand(25, 90, 70).astype(np.float32)
            np.savez(npz_path, imgs=volume, spacing=np.array([1.5, 0.8, 0.8], dtype=np.float32))

            service = DicomZipToNpzService()
            service.convert_npz_to_nifti(npz_path=npz_path, output_nifti_path=nifti_path)

            nii = nib.load(nifti_path)
            self.assertEqual(tuple(nii.shape), (25, 90, 70))


class StudyCreateSerializerValidationTest(TestCase):
    def test_accepts_nifti_extensions(self):
        required_payload = {
            'case_identification': 'CASE-001',
            'patient_name': 'John Doe',
            'age': 45,
            'exam_source': 'PACS',
            'exam_modality': 'CT',
            'category_id': 'abdomen',
        }
        serializer_nii = StudyCreateSerializer(
            data={**required_payload, 'file': SimpleUploadedFile('sample.nii', b'dummy')}
        )
        self.assertTrue(serializer_nii.is_valid(), serializer_nii.errors)
        self.assertEqual(serializer_nii.validated_data['upload_type'], 'nifti')

        serializer_niigz = StudyCreateSerializer(
            data={**required_payload, 'file': SimpleUploadedFile('sample.nii.gz', b'dummy')}
        )
        self.assertTrue(serializer_niigz.is_valid(), serializer_niigz.errors)
        self.assertEqual(serializer_niigz.validated_data['upload_type'], 'nifti')

    def test_rejects_missing_required_metadata(self):
        serializer = StudyCreateSerializer(
            data={'file': SimpleUploadedFile('sample.npz', b'dummy')}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('case_identification', serializer.errors)
        self.assertIn('patient_name', serializer.errors)
        self.assertIn('age', serializer.errors)
        self.assertIn('exam_source', serializer.errors)
        self.assertIn('exam_modality', serializer.errors)
        self.assertIn('category_id', serializer.errors)

    def test_rejects_missing_file_with_field_error(self):
        serializer = StudyCreateSerializer(
            data={
                'case_identification': 'CASE-001',
                'patient_name': 'John Doe',
                'age': 45,
                'exam_source': 'PACS',
                'exam_modality': 'CT',
                'category_id': 'abdomen',
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)

    def test_rejects_unrecognized_file_field_name_with_hint(self):
        serializer = StudyCreateSerializer(
            data={
                'case_identification': 'CASE-001',
                'patient_name': 'John Doe',
                'age': 45,
                'exam_source': 'PACS',
                'exam_modality': 'CT',
                'category_id': 'abdomen',
                'nifti': SimpleUploadedFile('sample.nii.gz', b'dummy'),
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('file', serializer.errors)
        self.assertIn('Received file-like keys: nifti', str(serializer.errors['file'][0]))


class StudyUploadMetadataErrorMappingTest(TestCase):
    def test_maps_invalid_exam_modality_to_field_error(self):
        mapped = StudyViewSet._map_upload_metadata_error("Invalid exam_modality: XR")
        self.assertEqual(mapped, {"exam_modality": ["Invalid exam_modality: XR"]})

    def test_maps_invalid_category_to_field_error(self):
        mapped = StudyViewSet._map_upload_metadata_error("Invalid category_id: abc")
        self.assertEqual(mapped, {"category_id": ["Invalid category_id: abc"]})

    def test_maps_target_modality_mismatch_to_both_fields(self):
        mapped = StudyViewSet._map_upload_metadata_error("Selected target does not belong to exam_modality")
        self.assertIn("category_id", mapped)
        self.assertIn("exam_modality", mapped)


class StudyStatusEndpointTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            email='terminal@example.com',
            cognito_sub='terminal-sub',
            role='INDIVIDUAL',
        )

    @patch('apps.studies.views.InferenceClient.get_status')
    def test_completed_study_status_does_not_call_inference_api(self, mock_get_status):
        study = Study.objects.create(
            clinic=None,
            owner=self.user,
            category='MRI: head',
            status='COMPLETED',
            inference_job_id='remote-job-123',
        )

        view = StudyViewSet.as_view({'get': 'status'})
        request = self.factory.get(f'/api/studies/{study.id}/status/')
        force_authenticate(request, user=self.user)

        response = view(request, pk=study.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'COMPLETED')
        mock_get_status.assert_not_called()
