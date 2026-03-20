import os
import tempfile
import zipfile

import nibabel as nib
import numpy as np
from django.test import TestCase

from apps.accounts.models import User
from apps.inference.executors.biomedparse_ecs_executor import BiomedParseECSExecutor
from apps.inference.executors.preprocessing_executor import InferencePreprocessor
from apps.inference.models import InferenceJob, ModelVersion, Tenant
from apps.inference.object_layout import output_mask_npz_key, output_summary_key
from apps.inference.prompt_catalog import build_text_prompts_for_job
from apps.inference.state_machine import transition_job
from services.dicom_pipeline import DicomZipToNpzService
from services.nifti_converter import NiftiConverter


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
                self.assertEqual(
                    tuple(npz_data["imgs"].shape),
                    tuple(np.transpose(input_volume_xyz, (2, 1, 0)).shape),
                )

            restored_nifti = nib.load(prepared["original_nifti"])
            self.assertEqual(tuple(restored_nifti.shape), tuple(input_volume_xyz.shape))

    def test_preprocess_existing_npz_injects_text_prompts_when_missing(self):
        service = DicomZipToNpzService()

        with tempfile.TemporaryDirectory() as tmpdir:
            npz_path = os.path.join(tmpdir, "input.npz")
            out_path = os.path.join(tmpdir, "output.npz")
            np.savez_compressed(npz_path, imgs=np.zeros((8, 7, 5), dtype=np.float32))

            service.preprocess_existing_npz(
                npz_path=npz_path,
                output_npz_path=out_path,
                exam_modality="MRI",
                category_hint="head",
                text_prompts={"1": "multiple sclerosis lesion", "instance_label": 0},
            )

            with np.load(out_path, allow_pickle=True) as npz_data:
                prompts = npz_data["text_prompts"].item()
                self.assertEqual(prompts.get("1"), "multiple sclerosis lesion")
                self.assertEqual(prompts.get("instance_label"), 0)


class NiftiConverterAlignmentTest(TestCase):
    def test_align_mask_transposes_axes_when_shapes_are_permuted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Reference image in XYZ layout (typical original NIfTI upload).
            reference_shape = (8, 7, 5)
            reference_data = np.zeros(reference_shape, dtype=np.float32)
            reference_path = os.path.join(tmpdir, "original_image.nii.gz")
            nib.save(nib.Nifti1Image(reference_data, np.eye(4)), reference_path)

            # Mask in ZYX layout (typical model output after XYZ->ZYX preprocessing).
            mask_zyx = np.zeros((5, 7, 8), dtype=np.uint8)
            mask_zyx[2, 3, 4] = 1
            mask_zyx[1, 2, 6] = 1
            mask_path = os.path.join(tmpdir, "mask_raw.nii.gz")
            nib.save(nib.Nifti1Image(mask_zyx, np.eye(4)), mask_path)

            aligned_path = os.path.join(tmpdir, "mask_aligned.nii.gz")
            ok = NiftiConverter.align_mask_to_reference(
                mask_nifti_path=mask_path,
                reference_nifti_path=reference_path,
                output_path=aligned_path,
            )
            self.assertTrue(ok)

            aligned = np.asarray(nib.load(aligned_path).get_fdata(), dtype=np.uint8)
            self.assertEqual(tuple(aligned.shape), reference_shape)

            # Expected voxel locations after transpose (2,1,0): (x,y,z) from (z,y,x).
            self.assertEqual(int(aligned[4, 3, 2]), 1)
            self.assertEqual(int(aligned[6, 2, 1]), 1)

            # Axis transpose must preserve voxel count (resize would usually change this).
            self.assertEqual(int(aligned.sum()), int(mask_zyx.sum()))

    def test_align_mask_uses_deterministic_inverse_transpose_for_ambiguous_shapes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Ambiguous case: two equal in-plane dimensions (X == Y).
            reference_shape = (256, 256, 23)
            reference_data = np.zeros(reference_shape, dtype=np.float32)
            reference_path = os.path.join(tmpdir, "original_image.nii.gz")
            nib.save(nib.Nifti1Image(reference_data, np.eye(4)), reference_path)

            # Model output in ZYX layout.
            mask_zyx = np.zeros((23, 256, 256), dtype=np.uint8)
            mask_zyx[10, 20, 30] = 1
            mask_zyx[3, 180, 40] = 1
            mask_path = os.path.join(tmpdir, "mask_raw.nii.gz")
            nib.save(nib.Nifti1Image(mask_zyx, np.eye(4)), mask_path)

            aligned_path = os.path.join(tmpdir, "mask_aligned.nii.gz")
            ok = NiftiConverter.align_mask_to_reference(
                mask_nifti_path=mask_path,
                reference_nifti_path=reference_path,
                output_path=aligned_path,
            )
            self.assertTrue(ok)

            aligned = np.asarray(nib.load(aligned_path).get_fdata(), dtype=np.uint8)
            self.assertEqual(tuple(aligned.shape), reference_shape)

            # Correct inverse transpose is (2,1,0): (z,y,x) -> (x,y,z)
            self.assertEqual(int(aligned[30, 20, 10]), 1)
            self.assertEqual(int(aligned[40, 180, 3]), 1)

            # Wrong ambiguous transpose (1,2,0) would swap X/Y and hit these coords.
            self.assertEqual(int(aligned[20, 30, 10]), 0)
            self.assertEqual(int(aligned[180, 40, 3]), 0)


class InferencePromptCatalogTest(TestCase):
    def test_build_text_prompts_from_category_catalog(self):
        prompts = build_text_prompts_for_job(
            exam_modality="MRI",
            category_id="head_tumor_cerebral",
        )
        self.assertIn("instance_label", prompts)
        self.assertEqual(prompts["instance_label"], 0)
        self.assertIn("1", prompts)
        self.assertTrue(str(prompts["1"]).strip())

    def test_build_text_prompts_has_safe_fallback(self):
        prompts = build_text_prompts_for_job(
            exam_modality="MRI",
            category_id="unknown-category",
        )
        self.assertEqual(prompts.get("instance_label"), 0)
        self.assertIn("1", prompts)

    def test_build_text_prompts_has_global_fallback_when_metadata_missing(self):
        prompts = build_text_prompts_for_job(
            exam_modality="",
            category_id="",
        )
        self.assertEqual(prompts.get("instance_label"), 0)
        self.assertIn("1", prompts)


class _FakeS3:
    def __init__(self, existing_keys):
        self.existing_keys = set(existing_keys)

    def generate_presigned_url(self, key, expires_in, method, extra_params=None):
        return f"https://example.invalid/{key}?method={method}"

    def object_exists(self, key):
        return key in self.existing_keys

    def download_file(self, key, destination):
        if key not in self.existing_keys:
            return False
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as output_file:
            output_file.write(b"ok")
        return True


class _FakeECS:
    def __init__(self, describe_responses):
        self.describe_responses = list(describe_responses)
        self.describe_calls = 0

    def run_task(self, **kwargs):
        return {
            "tasks": [
                {
                    "taskArn": "arn:aws:ecs:us-east-1:123456789012:task/test-cluster/task-id",
                }
            ],
            "failures": [],
        }

    def describe_tasks(self, **kwargs):
        if self.describe_calls < len(self.describe_responses):
            response = self.describe_responses[self.describe_calls]
        elif self.describe_responses:
            response = self.describe_responses[-1]
        else:
            response = {"tasks": [], "failures": []}
        self.describe_calls += 1
        return response


class BiomedParseECSExecutorTest(TestCase):
    def _build_executor(self, fake_s3, fake_ecs, *, missing_grace_seconds=0):
        executor = BiomedParseECSExecutor.__new__(BiomedParseECSExecutor)
        executor.s3 = fake_s3
        executor.ecs_client = fake_ecs
        executor.cluster = "test-cluster"
        executor.task_definition = "task-def:1"
        executor.capacity_provider = "test-cp"
        executor.subnets = ["subnet-123"]
        executor.security_groups = ["sg-123"]
        executor.container_name = "biomedparse"
        executor.poll_seconds = 1
        executor.timeout_seconds = 60
        executor.presign_expires_seconds = 900
        executor.task_not_found_grace_seconds = missing_grace_seconds
        return executor

    def test_run_succeeds_when_task_missing_but_outputs_exist(self):
        tenant_id = "tenant-1"
        job_id = "job-1"
        mask_key = output_mask_npz_key(tenant_id, job_id)
        summary_key = output_summary_key(tenant_id, job_id)

        fake_s3 = _FakeS3(existing_keys={mask_key, summary_key})
        fake_ecs = _FakeECS(
            describe_responses=[
                {
                    "tasks": [],
                    "failures": [{"arn": "arn:missing", "reason": "MISSING"}],
                }
            ]
        )
        executor = self._build_executor(fake_s3, fake_ecs, missing_grace_seconds=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = executor.run(
                job_id=job_id,
                tenant_id=tenant_id,
                normalized_input_key="normalized/test/input.npz",
                work_dir=tmpdir,
                requested_device="cuda",
            )
            self.assertTrue(os.path.exists(outputs["mask_npz_local"]))
            self.assertTrue(os.path.exists(outputs["summary_json_local"]))

        self.assertEqual(outputs["mask_npz_key"], mask_key)
        self.assertEqual(outputs["summary_key"], summary_key)

    def test_run_raises_when_task_missing_and_outputs_absent(self):
        tenant_id = "tenant-2"
        job_id = "job-2"
        fake_s3 = _FakeS3(existing_keys=set())
        fake_ecs = _FakeECS(
            describe_responses=[
                {
                    "tasks": [],
                    "failures": [{"arn": "arn:missing", "reason": "MISSING"}],
                }
            ]
        )
        executor = self._build_executor(fake_s3, fake_ecs, missing_grace_seconds=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError) as raised:
                executor.run(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    normalized_input_key="normalized/test/input.npz",
                    work_dir=tmpdir,
                    requested_device="cuda",
                )

        self.assertIn("ECS task not found", str(raised.exception))
