from django.test import TestCase, RequestFactory
from django.test import override_settings
import os
import tempfile
import numpy as np
import json
from pathlib import Path

from apps.accounts.models import User
from apps.accounts.permissions import TenantQuerySetMixin
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.studies.models import Study
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
    def test_preprocess_existing_npz_resizes_and_resamples(self):
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
                self.assertEqual(tuple(data['imgs'].shape), (32, 64, 64))
                self.assertEqual(data['imgs'].dtype, np.float16)


class CategoryResolutionTest(TestCase):
    def test_resolve_category_from_modality_target_catalog(self):
        catalog = {
            "version": "test",
            "modalities": [
                {
                    "id": "ct",
                    "name": "CT",
                    "targets": [
                        {
                            "id": "ct_liver_tumors",
                            "name": "liver tumors",
                            "prompt": "Visualization of liver tumors in CT",
                        }
                    ],
                },
                {
                    "id": "mri",
                    "name": "MRI",
                    "targets": [
                        {
                            "id": "mri_glioma",
                            "name": "glioma",
                            "prompt": "Visualization of glioma in MRI",
                        }
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            data_dir = base_dir / 'data'
            data_dir.mkdir(parents=True, exist_ok=True)
            with open(data_dir / 'categories.json', 'w') as f:
                json.dump(catalog, f)

            with override_settings(BASE_DIR=base_dir):
                category_name, prompt = StudyViewSet._resolve_category_and_prompt('mri_glioma')

        self.assertEqual(category_name, 'MRI: glioma')
        self.assertEqual(prompt, 'Visualization of glioma in MRI')
