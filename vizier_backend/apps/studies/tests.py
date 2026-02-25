from django.test import TestCase, RequestFactory

from apps.accounts.models import User
from apps.accounts.permissions import TenantQuerySetMixin
from apps.audit.models import AuditLog
from apps.audit.services import AuditService
from apps.studies.models import Study
from apps.tenants.models import Clinic


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
