import os
import tempfile
import zipfile

import nibabel as nib
import numpy as np
from django.test import TestCase

from apps.accounts.models import User
from apps.inference.executors.preprocessing_executor import InferencePreprocessor
from apps.inference.models import InferenceJob, ModelVersion, Tenant
from apps.inference.state_machine import transition_job


class InferenceDomainTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="inference-user@example.com",
            cognito_sub="inference-user-sub",
            role="INDIVIDUAL",
        )

    def test_resolve_tenant_for_individual(self):
        tenant = Tenant.resolve_for_user(self.user)
        self.assertEqual(tenant.type, Tenant.TYPE_INDIVIDUAL)
        self.assertEqual(tenant.owner_user_id, self.user.id)
        self.assertIsNone(tenant.clinic_id)

    def test_transition_is_idempotent_for_invalid_or_same_state(self):
        tenant = Tenant.resolve_for_user(self.user)
        model_version = ModelVersion.objects.create(name="biomedparse", version="v1")
        job = InferenceJob.objects.create(
            tenant=tenant,
            owner=self.user,
            requested_model_version=model_version,
            status=InferenceJob.STATUS_CREATED,
            correlation_id="corr-1",
        )

        changed = transition_job(job=job, to_status=InferenceJob.STATUS_UPLOAD_PENDING)
        self.assertTrue(changed.changed)

        noop_same = transition_job(job=job, to_status=InferenceJob.STATUS_UPLOAD_PENDING)
        self.assertFalse(noop_same.changed)

        noop_invalid = transition_job(job=job, to_status=InferenceJob.STATUS_COMPLETED)
        self.assertFalse(noop_invalid.changed)


class InferencePreprocessorTest(TestCase):
    def test_prepare_input_accepts_zipped_nifti(self):
        preprocessor = InferencePreprocessor()

        with tempfile.TemporaryDirectory() as tmpdir:
            input_volume_xyz = np.arange(6 * 7 * 5, dtype=np.float32).reshape((6, 7, 5))
            nifti_path = os.path.join(tmpdir, "training02_01_flair.nii")
            nifti_image = nib.Nifti1Image(input_volume_xyz, affine=np.eye(4))
            nib.save(nifti_image, nifti_path)

            zip_path = os.path.join(tmpdir, "training02_01_flair.nii.zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(nifti_path, arcname="nested/training02_01_flair.nii")

            work_dir = os.path.join(tmpdir, "work")
            prepared = preprocessor.prepare_input(
                input_file_path=zip_path,
                work_dir=work_dir,
                text_prompts={"organ": "brain"},
                exam_modality="mri",
                category_hint="brain",
            )

            self.assertTrue(os.path.exists(prepared["normalized_input_npz"]))
            self.assertTrue(os.path.exists(prepared["original_nifti"]))

            with np.load(prepared["normalized_input_npz"], allow_pickle=True) as npz_data:
                self.assertIn("imgs", npz_data.files)
                self.assertEqual(npz_data["imgs"].ndim, 3)

            restored_nifti = nib.load(prepared["original_nifti"])
            self.assertEqual(tuple(restored_nifti.shape), tuple(input_volume_xyz.shape))
