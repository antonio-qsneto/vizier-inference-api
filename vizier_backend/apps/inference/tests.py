from django.test import TestCase

from apps.accounts.models import User
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
