from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.rbac import (
    RBACPermission,
    RBACRole,
    has_scoped_permission,
    resolve_effective_role,
)
from apps.tenants.models import Clinic, Membership


class ScopedRBACPolicyTest(TestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user(
            email='rbac-owner-a@example.com',
            cognito_sub='rbac-owner-a-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic_a = Clinic.objects.create(
            name='RBAC Clinic A',
            owner=self.owner_a,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            seat_limit=5,
        )
        self.owner_a.clinic = self.clinic_a
        self.owner_a.save(update_fields=['clinic', 'updated_at'])
        Membership.objects.create(
            account=self.clinic_a,
            user=self.owner_a,
            role=Membership.ROLE_ADMIN,
        )

        self.owner_b = User.objects.create_user(
            email='rbac-owner-b@example.com',
            cognito_sub='rbac-owner-b-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic_b = Clinic.objects.create(
            name='RBAC Clinic B',
            owner=self.owner_b,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            seat_limit=5,
        )
        self.owner_b.clinic = self.clinic_b
        self.owner_b.save(update_fields=['clinic', 'updated_at'])
        Membership.objects.create(
            account=self.clinic_b,
            user=self.owner_b,
            role=Membership.ROLE_ADMIN,
        )

        self.admin = User.objects.create_user(
            email='rbac-admin@example.com',
            cognito_sub='rbac-admin-sub',
            role='CLINIC_ADMIN',
            clinic=self.clinic_a,
        )
        Membership.objects.create(
            account=self.clinic_a,
            user=self.admin,
            role=Membership.ROLE_ADMIN,
        )

        self.doctor = User.objects.create_user(
            email='rbac-doctor@example.com',
            cognito_sub='rbac-doctor-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic_a,
        )
        Membership.objects.create(
            account=self.clinic_a,
            user=self.doctor,
            role=Membership.ROLE_DOCTOR,
        )

        self.individual = User.objects.create_user(
            email='rbac-individual@example.com',
            cognito_sub='rbac-individual-sub',
            role='INDIVIDUAL',
        )

        self.platform_admin = User.objects.create_user(
            email='rbac-platform-admin@example.com',
            cognito_sub='rbac-platform-admin-sub',
            role='INDIVIDUAL',
            is_staff=True,
            is_superuser=True,
        )

    def test_role_resolution_prioritizes_membership_role(self):
        self.admin.role = 'CLINIC_DOCTOR'
        self.admin.save(update_fields=['role', 'updated_at'])

        self.assertEqual(resolve_effective_role(self.admin), RBACRole.CLINIC_ADMIN)

    def test_clinic_admin_billing_permission_is_tenant_scoped(self):
        self.assertTrue(
            has_scoped_permission(
                self.admin,
                RBACPermission.BILLING_CLINIC_MANAGE,
                tenant_id=self.clinic_a.id,
            )
        )
        self.assertFalse(
            has_scoped_permission(
                self.admin,
                RBACPermission.BILLING_CLINIC_MANAGE,
                tenant_id=self.clinic_b.id,
            )
        )

    def test_clinic_admin_cannot_create_studies(self):
        self.assertFalse(
            has_scoped_permission(
                self.admin,
                RBACPermission.STUDIES_CREATE,
                tenant_id=self.clinic_a.id,
            )
        )

    def test_clinic_doctor_cannot_manage_clinic_billing(self):
        self.assertFalse(
            has_scoped_permission(
                self.doctor,
                RBACPermission.BILLING_CLINIC_MANAGE,
                tenant_id=self.clinic_a.id,
            )
        )

    def test_individual_billing_permission_is_owner_scoped(self):
        self.assertTrue(
            has_scoped_permission(
                self.individual,
                RBACPermission.BILLING_INDIVIDUAL_MANAGE,
                resource_owner_user_id=self.individual.id,
            )
        )
        self.assertFalse(
            has_scoped_permission(
                self.individual,
                RBACPermission.BILLING_INDIVIDUAL_MANAGE,
                resource_owner_user_id=self.admin.id,
            )
        )

    def test_platform_admin_has_global_permission_bypass(self):
        self.assertTrue(
            has_scoped_permission(
                self.platform_admin,
                RBACPermission.BILLING_CLINIC_MANAGE,
                tenant_id=self.clinic_b.id,
            )
        )
        self.assertTrue(
            has_scoped_permission(
                self.platform_admin,
                RBACPermission.BILLING_INDIVIDUAL_MANAGE,
                resource_owner_user_id=self.individual.id,
            )
        )
