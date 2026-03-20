from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from datetime import timedelta

from apps.accounts.models import User, UserNotice, UserSubscription
from apps.audit.models import AuditLog
from apps.tenants.models import Clinic, DoctorInvitation, Membership


class ClinicCreateApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='clinic-admin@example.com',
            cognito_sub='clinic-admin-sub',
            role='INDIVIDUAL',
        )
        self.client.force_authenticate(user=self.user)

    def test_create_clinic_endpoint_is_blocked_until_checkout_completion(self):
        response = self.client.post(
            '/api/clinics/clinics/',
            {'name': 'My Clinic', 'cnpj': '12345678000199'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn('checkout', response.data['detail'].lower())
        self.assertFalse(Clinic.objects.filter(owner=self.user).exists())

    def test_create_clinic_fails_if_user_already_in_clinic(self):
        owner = User.objects.create_user(
            email='owner@example.com',
            cognito_sub='owner-sub',
            role='CLINIC_ADMIN',
        )
        clinic = Clinic.objects.create(name='Existing Clinic', owner=owner)
        self.user.clinic = clinic
        self.user.save(update_fields=['clinic'])

        response = self.client.post(
            '/api/clinics/clinics/',
            {'name': 'Another Clinic'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_create_clinic_fails_if_user_already_owns_clinic(self):
        Clinic.objects.create(name='Owned Clinic', owner=self.user)

        response = self.client.post(
            '/api/clinics/clinics/',
            {'name': 'Another Clinic'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_create_clinic_fails_for_active_paid_individual_subscription(self):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            current_period_end=timezone.now() + timedelta(days=14),
        )

        response = self.client.post(
            '/api/clinics/clinics/',
            {'name': 'Blocked Clinic', 'cnpj': '12345678000199'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn('assinatura individual ativa', response.data['detail'])

    def test_create_clinic_fails_for_canceled_paid_subscription_until_period_end(self):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
            status=UserSubscription.STATUS_CANCELED,
            current_period_end=timezone.now() + timedelta(days=5),
        )

        response = self.client.post(
            '/api/clinics/clinics/',
            {'name': 'Blocked Clinic', 'cnpj': '12345678000199'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)


class ClinicDoctorRemovalApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_user(
            email='admin@example.com',
            cognito_sub='admin-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Main Clinic',
            owner=self.admin,
        )
        self.admin.clinic = self.clinic
        self.admin.save(update_fields=['clinic', 'updated_at'])

        self.doctor = User.objects.create_user(
            email='doctor@example.com',
            cognito_sub='doctor-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        self.invitation = DoctorInvitation.objects.create(
            clinic=self.clinic,
            email=self.doctor.email,
            invited_by=self.admin,
            status='ACCEPTED',
            expires_at=timezone.now() + timedelta(days=7),
            accepted_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.admin)

    def test_remove_doctor_detaches_clinic_and_downgrades_role(self):
        response = self.client.delete(
            f'/api/clinics/clinics/remove_doctor/?doctor_id={self.doctor.id}',
        )

        self.assertEqual(response.status_code, 200)

        self.doctor.refresh_from_db()
        self.invitation.refresh_from_db()
        self.assertIsNone(self.doctor.clinic)
        self.assertEqual(self.doctor.role, 'INDIVIDUAL')
        self.assertTrue(self.doctor.is_active)
        self.assertEqual(self.invitation.status, 'REMOVED')
        self.assertTrue(
            UserNotice.objects.filter(
                user=self.doctor,
                type=UserNotice.TYPE_CLINIC_REMOVED,
                acknowledged_at__isnull=True,
            ).exists()
        )

    def test_doctors_list_returns_only_clinic_doctors(self):
        response = self.client.get('/api/clinics/clinics/doctors/')

        self.assertEqual(response.status_code, 200)
        returned_ids = {item['id'] for item in response.data}

        self.assertIn(self.doctor.id, returned_ids)
        self.assertNotIn(self.admin.id, returned_ids)

    def test_removed_doctor_no_longer_has_clinic_in_me_endpoint(self):
        self.client.delete(f'/api/clinics/clinics/remove_doctor/?doctor_id={self.doctor.id}')

        self.doctor.refresh_from_db()
        self.client.force_authenticate(user=self.doctor)

        response = self.client.get('/api/auth/me/')

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['clinic_id'])
        self.assertEqual(response.data['role'], 'INDIVIDUAL')


class ClinicDoctorVisibilityAndSelfUnlinkApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_user(
            email='visibility-admin@example.com',
            cognito_sub='visibility-admin-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Visibility Clinic',
            owner=self.admin,
            subscription_plan=Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            seat_limit=3,
        )
        self.admin.clinic = self.clinic
        self.admin.save(update_fields=['clinic', 'updated_at'])
        Membership.objects.create(
            account=self.clinic,
            user=self.admin,
            role=Membership.ROLE_ADMIN,
        )

        self.doctor = User.objects.create_user(
            email='visibility-doctor@example.com',
            cognito_sub='visibility-doctor-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        Membership.objects.create(
            account=self.clinic,
            user=self.doctor,
            role=Membership.ROLE_DOCTOR,
        )

        self.client.force_authenticate(user=self.doctor)

    def test_clinic_list_is_redacted_for_clinic_doctor(self):
        response = self.client.get('/api/clinics/clinics/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        clinic_payload = response.data['results'][0]
        self.assertEqual(set(clinic_payload.keys()), {'id', 'name'})
        self.assertEqual(clinic_payload['name'], self.clinic.name)

    def test_clinic_retrieve_is_redacted_for_clinic_doctor(self):
        response = self.client.get(f'/api/clinics/clinics/{self.clinic.id}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data.keys()), {'id', 'name'})
        self.assertEqual(response.data['name'], self.clinic.name)

    def test_me_profile_redacts_clinic_billing_sensitive_fields_for_doctor(self):
        response = self.client.get('/api/auth/users/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['effective_role'], 'clinic_doctor')
        self.assertIsNone(response.data['subscription_plan'])
        self.assertIsNone(response.data['seat_limit'])
        self.assertIsNone(response.data['seat_used'])
        self.assertIsNone(response.data['account_status'])

    @patch('apps.tenants.views.schedule_seat_reduction')
    def test_leave_clinic_detaches_doctor_and_sets_free_subscription(
        self,
        schedule_seat_reduction_mock,
    ):
        response = self.client.post('/api/clinics/clinics/leave_clinic/', format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['new_role'], 'INDIVIDUAL')
        self.assertIsNone(response.data['clinic_id'])
        self.assertEqual(response.data['subscription_plan'], 'free')

        self.doctor.refresh_from_db()
        self.assertIsNone(self.doctor.clinic)
        self.assertEqual(self.doctor.role, 'INDIVIDUAL')
        self.assertFalse(
            Membership.objects.filter(
                account=self.clinic,
                user=self.doctor,
                role=Membership.ROLE_DOCTOR,
            ).exists()
        )

        subscription = UserSubscription.objects.get(user=self.doctor)
        self.assertEqual(subscription.plan, UserSubscription.PLAN_FREE)
        self.assertEqual(subscription.status, UserSubscription.STATUS_INACTIVE)
        self.assertIsNone(subscription.stripe_subscription_id)
        self.assertIsNone(subscription.current_period_end)

        schedule_seat_reduction_mock.assert_not_called()

    def test_leave_clinic_rejects_non_doctor_members(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/clinics/clinics/leave_clinic/', format='json')
        self.assertEqual(response.status_code, 403)


class ClinicDoctorInviteApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='owner@example.com',
            cognito_sub='owner-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Invite Clinic',
            owner=self.admin,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            seat_limit=10,
        )
        self.admin.clinic = self.clinic
        self.admin.save(update_fields=['clinic', 'updated_at'])
        self.client.force_authenticate(user=self.admin)

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_returns_400_when_pending_invitation_exists(self, send_email_mock):
        DoctorInvitation.objects.create(
            clinic=self.clinic,
            email='doctor@example.com',
            invited_by=self.admin,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'doctor@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'Invitation already sent to this email')
        send_email_mock.assert_not_called()

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_reopens_removed_invitation_instead_of_creating_duplicate(self, send_email_mock):
        invitation = DoctorInvitation.objects.create(
            clinic=self.clinic,
            email='doctor@example.com',
            invited_by=self.admin,
            status='REMOVED',
            expires_at=timezone.now() - timedelta(days=1),
            accepted_at=timezone.now() - timedelta(days=2),
        )

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'doctor@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'PENDING')
        self.assertIsNone(invitation.accepted_at)
        self.assertEqual(
            DoctorInvitation.objects.filter(clinic=self.clinic, email='doctor@example.com').count(),
            1,
        )
        send_email_mock.assert_called_once_with(invitation)

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_sends_email(self, send_email_mock):
        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'doctor@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)

        invitation = DoctorInvitation.objects.get(clinic=self.clinic, email='doctor@example.com')
        send_email_mock.assert_called_once_with(invitation)

    @patch('apps.tenants.views.send_doctor_invitation_email', side_effect=RuntimeError('smtp down'))
    def test_invite_rolls_back_when_email_sending_fails(self, send_email_mock):
        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'doctor@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data['error'], 'Failed to send invitation')
        self.assertFalse(
            DoctorInvitation.objects.filter(clinic=self.clinic, email='doctor@example.com').exists()
        )
        send_email_mock.assert_called_once()

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_blocks_existing_clinic_admin_account(self, send_email_mock):
        User.objects.create_user(
            email='admin2@example.com',
            cognito_sub='admin2-sub',
            role='CLINIC_ADMIN',
        )

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'admin2@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['error'],
            'This account already belongs to a clinic and cannot be invited as a doctor.',
        )
        send_email_mock.assert_not_called()

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_blocks_user_with_admin_membership_even_if_role_drifted(self, send_email_mock):
        other_owner = User.objects.create_user(
            email='other-owner@example.com',
            cognito_sub='other-owner-sub',
            role='CLINIC_ADMIN',
        )
        other_clinic = Clinic.objects.create(
            name='Other Clinic',
            owner=other_owner,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            seat_limit=3,
        )
        other_owner.clinic = other_clinic
        other_owner.save(update_fields=['clinic', 'updated_at'])
        Membership.objects.create(
            account=other_clinic,
            user=other_owner,
            role=Membership.ROLE_ADMIN,
        )

        drifted_admin = User.objects.create_user(
            email='drifted-admin@example.com',
            cognito_sub='drifted-admin-sub',
            role='CLINIC_DOCTOR',
            clinic=other_clinic,
        )
        Membership.objects.create(
            account=other_clinic,
            user=drifted_admin,
            role=Membership.ROLE_ADMIN,
        )

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'drifted-admin@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['error'],
            'This account already belongs to a clinic and cannot be invited as a doctor.',
        )
        send_email_mock.assert_not_called()

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_blocks_existing_clinic_doctor_account(self, send_email_mock):
        clinic_doctor = User.objects.create_user(
            email='doctor-in-other-clinic@example.com',
            cognito_sub='doctor-in-other-clinic-sub',
            role='CLINIC_DOCTOR',
        )
        other_owner = User.objects.create_user(
            email='other-owner-2@example.com',
            cognito_sub='other-owner-2-sub',
            role='CLINIC_ADMIN',
        )
        other_clinic = Clinic.objects.create(
            name='Clinic B',
            owner=other_owner,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            seat_limit=3,
        )
        clinic_doctor.clinic = other_clinic
        clinic_doctor.save(update_fields=['clinic', 'updated_at'])

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'doctor-in-other-clinic@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['error'],
            'This account already belongs to a clinic and cannot be invited as a doctor.',
        )
        send_email_mock.assert_not_called()

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_invite_blocks_user_with_active_individual_subscription(self, send_email_mock):
        paid_user = User.objects.create_user(
            email='paid-individual@example.com',
            cognito_sub='paid-individual-sub',
            role='INDIVIDUAL',
        )
        UserSubscription.objects.create(
            user=paid_user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            current_period_end=timezone.now() + timedelta(days=10),
        )

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'paid-individual@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['error'],
            'This account already has an active individual subscription and cannot be invited to a clinic.',
        )
        send_email_mock.assert_not_called()

    @patch('apps.tenants.views.send_doctor_invitation_email')
    def test_accept_invitation_blocks_when_seat_limit_is_reached(self, send_email_mock):
        self.clinic.seat_limit = 1
        self.clinic.save(update_fields=['seat_limit', 'updated_at'])

        occupied_doctor = User.objects.create_user(
            email='occupied-seat@example.com',
            cognito_sub='occupied-seat-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        Membership.objects.create(
            account=self.clinic,
            user=occupied_doctor,
            role=Membership.ROLE_DOCTOR,
        )

        invitee = User.objects.create_user(
            email='invitee-seat-limit@example.com',
            cognito_sub='invitee-seat-limit-sub',
            role='INDIVIDUAL',
        )

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': invitee.email},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data['error'],
            'Seat limit reached for this clinic plan. Remove a doctor before inviting another one.',
        )

        invitation = DoctorInvitation.objects.create(
            clinic=self.clinic,
            email=invitee.email,
            invited_by=self.admin,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_authenticate(user=invitee)
        accept_response = self.client.post(
            f'/api/clinics/doctor-invitations/{invitation.id}/accept/',
            format='json',
        )

        self.assertEqual(accept_response.status_code, 409)
        self.assertEqual(
            accept_response.data['error'],
            'Seat limit reached for this clinic. Ask an admin to free a seat before accepting this invitation.',
        )
        send_email_mock.assert_not_called()

    def test_cancel_marks_pending_invitation_as_removed(self):
        invitation = DoctorInvitation.objects.create(
            clinic=self.clinic,
            email='doctor@example.com',
            invited_by=self.admin,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(
            f'/api/clinics/doctor-invitations/{invitation.id}/cancel/',
        )

        self.assertEqual(response.status_code, 200)

        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'REMOVED')
        self.assertEqual(response.data['status'], 'REMOVED')

    def test_cancel_returns_400_for_non_pending_invitation(self):
        invitation = DoctorInvitation.objects.create(
            clinic=self.clinic,
            email='doctor@example.com',
            invited_by=self.admin,
            status='ACCEPTED',
            expires_at=timezone.now() + timedelta(days=7),
            accepted_at=timezone.now(),
        )

        response = self.client.post(
            f'/api/clinics/doctor-invitations/{invitation.id}/cancel/',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'Invitation is already ACCEPTED')

    def test_cancel_returns_404_for_invitation_from_other_clinic(self):
        other_admin = User.objects.create_user(
            email='other-admin@example.com',
            cognito_sub='other-admin-sub',
            role='CLINIC_ADMIN',
        )
        other_clinic = Clinic.objects.create(
            name='Other Clinic',
            owner=other_admin,
        )
        other_invitation = DoctorInvitation.objects.create(
            clinic=other_clinic,
            email='doctor@example.com',
            invited_by=other_admin,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(
            f'/api/clinics/doctor-invitations/{other_invitation.id}/cancel/',
        )

        self.assertEqual(response.status_code, 404)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='no-reply@vizier.com',
    INVITATION_PLATFORM_NAME='Vizier',
    INVITATION_LOGIN_URL='https://vizier.com/login',
)
class DoctorInvitationEmailTest(TestCase):
    def test_email_body_contains_login_link(self):
        from apps.tenants.emails import send_doctor_invitation_email

        admin = User.objects.create_user(
            email='owner@example.com',
            cognito_sub='owner-email-test',
            role='CLINIC_ADMIN',
            first_name='Antonio',
            last_name='Neto',
        )
        clinic = Clinic.objects.create(
            name='Invite Clinic',
            owner=admin,
        )
        invitation = DoctorInvitation.objects.create(
            clinic=clinic,
            email='doctor@example.com',
            invited_by=admin,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )

        send_doctor_invitation_email(invitation)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['doctor@example.com'])
        self.assertEqual(mail.outbox[0].from_email, 'no-reply@vizier.com')
        self.assertIn('https://vizier.com/login', mail.outbox[0].body)
        self.assertIn('Invite Clinic', mail.outbox[0].body)


@override_settings(
    ENABLE_STRIPE_BILLING=True,
    STRIPE_ALLOWED_REDIRECT_ORIGINS=[
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ],
)
class ClinicSeatBillingApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='seat-admin@example.com',
            cognito_sub='seat-admin-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Seat Clinic',
            owner=self.admin,
            subscription_plan=Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            stripe_subscription_id='sub_clinic_test',
            stripe_subscription_item_id='si_clinic_test',
            stripe_customer_id='cus_clinic_test',
            seat_limit=1,
        )
        self.admin.clinic = self.clinic
        self.admin.save(update_fields=['clinic', 'updated_at'])
        Membership.objects.create(
            account=self.clinic,
            user=self.admin,
            role=Membership.ROLE_ADMIN,
        )

        self.doctor = User.objects.create_user(
            email='seat-doctor@example.com',
            cognito_sub='seat-doctor-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        Membership.objects.create(
            account=self.clinic,
            user=self.doctor,
            role=Membership.ROLE_DOCTOR,
        )
        self.client.force_authenticate(user=self.admin)

    def test_clinic_doctor_cannot_access_clinic_billing_checkout(self):
        self.client.force_authenticate(user=self.doctor)

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_clinic_doctor_cannot_invite_team_members(self):
        self.client.force_authenticate(user=self.doctor)

        response = self.client.post(
            '/api/clinics/clinics/invite/',
            {'email': 'new-doctor@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    @patch('apps.tenants.views.update_subscription_price')
    @patch('apps.tenants.views.apply_subscription_payload')
    def test_billing_checkout_updates_existing_subscription_plan(
        self,
        apply_subscription_payload_mock,
        update_subscription_price_mock,
    ):
        update_subscription_price_mock.return_value = (
            {'id': 'sub_clinic_test', 'customer': 'cus_clinic_test'},
            'price_annual_test',
        )

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'subscription_updated')
        update_subscription_price_mock.assert_called_once_with(
            clinic=self.clinic,
            plan_id=Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY,
            quantity=1,
        )
        apply_subscription_payload_mock.assert_called_once()

    @patch('apps.tenants.views.update_subscription_price')
    @patch('apps.tenants.views.apply_subscription_payload')
    def test_billing_checkout_existing_subscription_ignores_requested_quantity(
        self,
        apply_subscription_payload_mock,
        update_subscription_price_mock,
    ):
        self.clinic.seat_limit = 2
        self.clinic.save(update_fields=['seat_limit', 'updated_at'])
        update_subscription_price_mock.return_value = (
            {'id': 'sub_clinic_test', 'customer': 'cus_clinic_test'},
            'price_monthly_test',
        )

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
                'quantity': 5,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        update_subscription_price_mock.assert_called_once_with(
            clinic=self.clinic,
            plan_id=Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            quantity=2,
        )
        apply_subscription_payload_mock.assert_called_once()

    @patch('apps.tenants.views.create_checkout_session')
    def test_billing_checkout_new_subscription_uses_requested_quantity(
        self,
        create_checkout_session_mock,
    ):
        self.clinic.stripe_subscription_id = None
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.save(update_fields=['stripe_subscription_id', 'account_status', 'updated_at'])

        create_checkout_session_mock.return_value = (
            {'id': 'cs_test_clinic_123', 'url': 'https://checkout.stripe.test/clinic'},
            'price_monthly_test',
            3,
        )

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
                'quantity': 3,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checkout_session_id'], 'cs_test_clinic_123')
        create_checkout_session_mock.assert_called_once_with(
            clinic=self.clinic,
            initiated_by_user_id=self.admin.id,
            plan_id=Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            success_url=(
                'http://localhost:3000/clinic?billing=success'
                '&session_id={CHECKOUT_SESSION_ID}'
            ),
            cancel_url='http://localhost:3000/clinic?billing=cancel',
            requested_quantity=3,
        )

    @patch('apps.tenants.views.create_checkout_session')
    def test_billing_checkout_rejects_disallowed_redirect_urls(
        self,
        create_checkout_session_mock,
    ):
        self.clinic.stripe_subscription_id = None
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.save(update_fields=['stripe_subscription_id', 'account_status', 'updated_at'])

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
                'success_url': 'https://evil.example.com/success',
                'cancel_url': 'https://evil.example.com/cancel',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('success_url', response.data['detail'])
        create_checkout_session_mock.assert_not_called()

    @patch('apps.tenants.views.create_customer_portal_session')
    def test_billing_portal_rejects_disallowed_return_url(
        self,
        create_customer_portal_session_mock,
    ):
        response = self.client.post(
            '/api/clinics/clinics/billing_portal/',
            {'return_url': 'https://evil.example.com/portal'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('return_url', response.data['detail'])
        create_customer_portal_session_mock.assert_not_called()

    @patch('apps.tenants.views.create_checkout_session')
    def test_billing_checkout_records_audit_event(
        self,
        create_checkout_session_mock,
    ):
        self.clinic.stripe_subscription_id = None
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.save(update_fields=['stripe_subscription_id', 'account_status', 'updated_at'])
        create_checkout_session_mock.return_value = (
            {'id': 'cs_test_audit_123', 'url': 'https://checkout.stripe.test/clinic'},
            'price_monthly_test',
            2,
        )

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
                'quantity': 2,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                clinic=self.clinic,
                user=self.admin,
                action='BILLING_CHECKOUT_CREATED',
            ).exists()
        )

    @patch('apps.tenants.views.retrieve_checkout_session')
    @patch('apps.tenants.views.retrieve_subscription')
    @patch('apps.tenants.views.apply_subscription_payload')
    def test_billing_sync_from_checkout_session_updates_clinic_stripe_ids(
        self,
        apply_subscription_payload_mock,
        retrieve_subscription_mock,
        retrieve_checkout_session_mock,
    ):
        self.clinic.subscription_plan = Clinic.SUBSCRIPTION_PLAN_FREE
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.stripe_customer_id = None
        self.clinic.stripe_subscription_id = None
        self.clinic.save(
            update_fields=[
                'subscription_plan',
                'account_status',
                'stripe_customer_id',
                'stripe_subscription_id',
                'updated_at',
            ]
        )

        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_test_sync_123',
            'status': 'complete',
            'customer': 'cus_sync_123',
            'subscription': 'sub_sync_123',
            'client_reference_id': str(self.clinic.id),
            'metadata': {
                'clinic_id': str(self.clinic.id),
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            },
        }
        retrieve_subscription_mock.return_value = {'id': 'sub_sync_123'}

        response = self.client.post(
            '/api/clinics/clinics/billing_sync/',
            {'checkout_session_id': 'cs_test_sync_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.stripe_customer_id, 'cus_sync_123')
        self.assertEqual(self.clinic.stripe_subscription_id, 'sub_sync_123')
        retrieve_checkout_session_mock.assert_called_once_with('cs_test_sync_123')
        retrieve_subscription_mock.assert_called_once_with('sub_sync_123')
        apply_subscription_payload_mock.assert_called_once()

    @patch('apps.tenants.views.retrieve_checkout_session')
    def test_billing_sync_returns_conflict_when_checkout_not_completed(
        self,
        retrieve_checkout_session_mock,
    ):
        self.clinic.subscription_plan = Clinic.SUBSCRIPTION_PLAN_FREE
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.stripe_customer_id = None
        self.clinic.stripe_subscription_id = None
        self.clinic.save(
            update_fields=[
                'subscription_plan',
                'account_status',
                'stripe_customer_id',
                'stripe_subscription_id',
                'updated_at',
            ]
        )

        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_test_pending_123',
            'status': 'open',
            'customer': 'cus_pending_123',
            'subscription': None,
            'client_reference_id': str(self.clinic.id),
            'metadata': {'clinic_id': str(self.clinic.id)},
        }

        response = self.client.post(
            '/api/clinics/clinics/billing_sync/',
            {'checkout_session_id': 'cs_test_pending_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)

    @patch('apps.tenants.views.retrieve_checkout_session')
    def test_billing_sync_requires_ownership_metadata(
        self,
        retrieve_checkout_session_mock,
    ):
        self.clinic.subscription_plan = Clinic.SUBSCRIPTION_PLAN_FREE
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.stripe_customer_id = None
        self.clinic.stripe_subscription_id = None
        self.clinic.save(
            update_fields=[
                'subscription_plan',
                'account_status',
                'stripe_customer_id',
                'stripe_subscription_id',
                'updated_at',
            ]
        )

        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_test_missing_owner_meta_123',
            'status': 'complete',
            'customer': 'cus_pending_123',
            'subscription': 'sub_pending_123',
            'metadata': {},
        }

        response = self.client.post(
            '/api/clinics/clinics/billing_sync/',
            {'checkout_session_id': 'cs_test_missing_owner_meta_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('ownership metadata', response.data['detail'])

    @patch('apps.tenants.views.retrieve_subscription')
    @patch('apps.tenants.views.apply_subscription_payload')
    def test_billing_sync_records_audit_event(
        self,
        apply_subscription_payload_mock,
        retrieve_subscription_mock,
    ):
        retrieve_subscription_mock.return_value = {'id': self.clinic.stripe_subscription_id}

        response = self.client.post(
            '/api/clinics/clinics/billing_sync/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        apply_subscription_payload_mock.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(
                clinic=self.clinic,
                user=self.admin,
                action='BILLING_SYNCED',
            ).exists()
        )

    def test_remove_doctor_yearly_does_not_change_contracted_seats(self):
        extra_doctor = User.objects.create_user(
            email='seat-doctor-yearly@example.com',
            cognito_sub='seat-doctor-yearly-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        Membership.objects.create(
            account=self.clinic,
            user=extra_doctor,
            role=Membership.ROLE_DOCTOR,
        )
        self.clinic.subscription_plan = Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY
        self.clinic.seat_limit = 2
        self.clinic.save(update_fields=['subscription_plan', 'seat_limit', 'updated_at'])

        response = self.client.delete(
            f'/api/clinics/clinics/remove_doctor/?doctor_id={extra_doctor.id}',
        )

        self.assertEqual(response.status_code, 200)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.seat_limit, 2)

    def test_remove_doctor_monthly_does_not_change_contracted_seats(self):
        replacement_doctor = User.objects.create_user(
            email='seat-doctor-2@example.com',
            cognito_sub='seat-doctor-2-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        Membership.objects.create(
            account=self.clinic,
            user=replacement_doctor,
            role=Membership.ROLE_DOCTOR,
        )
        self.clinic.seat_limit = 2
        self.clinic.save(update_fields=['seat_limit', 'updated_at'])

        response = self.client.delete(
            f'/api/clinics/clinics/remove_doctor/?doctor_id={replacement_doctor.id}',
        )

        self.assertEqual(response.status_code, 200)
        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.seat_limit, 2)

    def test_change_seats_endpoint_returns_gone(self):
        response = self.client.post(
            '/api/clinics/clinics/change_seats/',
            {'target_quantity': 2},
            format='json',
        )
        self.assertEqual(response.status_code, 410)

    def test_upgrade_seats_endpoint_returns_gone(self):
        response = self.client.post(
            '/api/clinics/clinics/upgrade_seats/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 410)

    def test_downgrade_to_individual_endpoint_is_gone(self):
        response = self.client.post(
            '/api/clinics/clinics/downgrade_to_individual/',
            format='json',
        )

        self.assertEqual(response.status_code, 410)

    def test_cancel_subscription_blocks_when_doctors_remain(self):
        response = self.client.post(
            '/api/clinics/clinics/cancel_subscription/',
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data['blockers'][0]['code'],
            'CLINIC_DOCTORS_REMAIN',
        )

    @patch('apps.tenants.views.cancel_clinic_subscription_at_period_end')
    def test_cancel_subscription_succeeds_when_requirements_are_met(
        self,
        cancel_clinic_subscription_mock,
    ):
        self.doctor.clinic = None
        self.doctor.role = 'INDIVIDUAL'
        self.doctor.save(update_fields=['clinic', 'role', 'updated_at'])
        Membership.objects.filter(
            account=self.clinic,
            user=self.doctor,
            role=Membership.ROLE_DOCTOR,
        ).delete()

        cancel_clinic_subscription_mock.return_value = {
            'id': 'sub_clinic_test',
            'customer': 'cus_clinic_test',
            'status': 'active',
            'cancel_at_period_end': True,
            'current_period_end': int((timezone.now() + timedelta(days=30)).timestamp()),
            'items': {
                'data': [
                    {
                        'id': 'si_clinic_test',
                        'quantity': 1,
                        'price': {'id': 'price_clinic_monthly_test'},
                    }
                ]
            },
        }

        response = self.client.post(
            '/api/clinics/clinics/cancel_subscription/',
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['account_status'], Clinic.ACCOUNT_STATUS_CANCELED)
        self.assertTrue(response.data['cancel_at_period_end'])

        self.clinic.refresh_from_db()
        self.assertEqual(self.clinic.account_status, Clinic.ACCOUNT_STATUS_CANCELED)
        self.assertTrue(self.clinic.cancel_at_period_end)
        self.assertIsNotNone(self.clinic.canceled_at)

    def test_cancel_subscription_blocks_when_pending_invitation_exists(self):
        DoctorInvitation.objects.create(
            clinic=self.clinic,
            email='pending-cancel@example.com',
            invited_by=self.admin,
            status='PENDING',
            expires_at=timezone.now() + timedelta(days=7),
        )

        response = self.client.post(
            '/api/clinics/clinics/cancel_subscription/',
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        blocker_codes = {item['code'] for item in response.data['blockers']}
        self.assertIn('CLINIC_PENDING_INVITATIONS', blocker_codes)

    def test_mutating_billing_endpoints_return_409_after_subscription_end(self):
        self.clinic.account_status = Clinic.ACCOUNT_STATUS_CANCELED
        self.clinic.cancel_at_period_end = False
        self.clinic.canceled_at = timezone.now() - timedelta(days=2)
        self.clinic.stripe_current_period_end = timezone.now() - timedelta(days=1)
        self.clinic.save(
            update_fields=[
                'account_status',
                'cancel_at_period_end',
                'canceled_at',
                'stripe_current_period_end',
                'updated_at',
            ]
        )

        checkout_response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY},
            format='json',
        )
        portal_response = self.client.post(
            '/api/clinics/clinics/billing_portal/',
            {},
            format='json',
        )
        change_seats_response = self.client.post(
            '/api/clinics/clinics/change_seats/',
            {'target_quantity': 1},
            format='json',
        )
        upgrade_seats_response = self.client.post(
            '/api/clinics/clinics/upgrade_seats/',
            {},
            format='json',
        )
        cancel_response = self.client.post(
            '/api/clinics/clinics/cancel_subscription/',
            format='json',
        )

        self.assertEqual(checkout_response.status_code, 409)
        self.assertEqual(portal_response.status_code, 409)
        self.assertEqual(change_seats_response.status_code, 409)
        self.assertEqual(upgrade_seats_response.status_code, 409)
        self.assertEqual(cancel_response.status_code, 409)

    @patch('apps.tenants.views.record_and_process_webhook_event')
    @patch('apps.tenants.views.construct_webhook_event')
    def test_clinic_webhook_endpoint_processes_events(
        self,
        construct_webhook_event_mock,
        record_and_process_webhook_event_mock,
    ):
        construct_webhook_event_mock.return_value = {
            'id': 'evt_test_clinic_1',
            'type': 'invoice.paid',
            'data': {'object': {}},
        }
        record_and_process_webhook_event_mock.return_value = True

        response = self.client.post(
            '/api/clinics/billing/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['processed'])


class ClinicCheckoutBeforeCreationApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='new-clinic-owner@example.com',
            cognito_sub='new-clinic-owner-sub',
            role='INDIVIDUAL',
        )
        self.client.force_authenticate(user=self.user)

    @patch('apps.tenants.views.create_checkout_session_for_new_clinic_owner')
    def test_billing_checkout_requires_clinic_name_for_user_without_clinic(
        self,
        create_checkout_mock,
    ):
        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
                'quantity': 2,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('clinic_name', response.data['detail'])
        create_checkout_mock.assert_not_called()

    @patch('apps.tenants.views.create_checkout_session_for_new_clinic_owner')
    def test_billing_checkout_without_clinic_starts_pending_checkout(
        self,
        create_checkout_mock,
    ):
        create_checkout_mock.return_value = (
            {'id': 'cs_pending_123', 'url': 'https://checkout.stripe.test/pending'},
            'price_monthly_test',
            3,
        )

        response = self.client.post(
            '/api/clinics/clinics/billing_checkout/',
            {
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
                'quantity': 3,
                'clinic_name': 'Nova Clínica',
                'cnpj': '12345678000199',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checkout_session_id'], 'cs_pending_123')
        create_checkout_mock.assert_called_once_with(
            owner_email=self.user.email,
            owner_user_id=self.user.id,
            plan_id=Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            success_url=(
                'http://localhost:3000/clinic?billing=success'
                '&session_id={CHECKOUT_SESSION_ID}'
            ),
            cancel_url='http://localhost:3000/clinic?billing=cancel',
            clinic_name='Nova Clínica',
            cnpj='12345678000199',
            requested_quantity=3,
        )

    @patch('apps.tenants.views.retrieve_checkout_session')
    def test_billing_sync_does_not_create_clinic_when_checkout_not_completed(
        self,
        retrieve_checkout_session_mock,
    ):
        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_pending_123',
            'status': 'open',
            'metadata': {
                'pending_clinic_owner_user_id': str(self.user.id),
                'pending_clinic_name': 'Nova Clínica',
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            },
            'subscription': None,
            'customer': None,
        }

        response = self.client.post(
            '/api/clinics/clinics/billing_sync/',
            {'checkout_session_id': 'cs_pending_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.clinic_id)
        self.assertFalse(Clinic.objects.filter(owner=self.user).exists())

    @patch('apps.tenants.views.retrieve_checkout_session')
    @patch('apps.tenants.views.retrieve_subscription')
    @patch('apps.tenants.views.apply_subscription_payload')
    def test_billing_sync_creates_clinic_only_after_checkout_completion(
        self,
        apply_subscription_payload_mock,
        retrieve_subscription_mock,
        retrieve_checkout_session_mock,
    ):
        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_complete_123',
            'status': 'complete',
            'customer': 'cus_new_123',
            'subscription': 'sub_new_123',
            'metadata': {
                'pending_clinic_owner_user_id': str(self.user.id),
                'pending_clinic_name': 'Nova Clínica',
                'pending_clinic_cnpj': '12345678000199',
                'plan_id': Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            },
        }
        retrieve_subscription_mock.return_value = {'id': 'sub_new_123'}

        response = self.client.post(
            '/api/clinics/clinics/billing_sync/',
            {'checkout_session_id': 'cs_complete_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.clinic_id)
        self.assertEqual(self.user.role, 'CLINIC_ADMIN')

        clinic = Clinic.objects.get(owner=self.user)
        self.assertEqual(clinic.name, 'Nova Clínica')
        self.assertEqual(clinic.cnpj, '12345678000199')
        self.assertEqual(clinic.stripe_customer_id, 'cus_new_123')
        self.assertEqual(clinic.stripe_subscription_id, 'sub_new_123')
        self.assertTrue(
            Membership.objects.filter(
                account=clinic,
                user=self.user,
                role=Membership.ROLE_ADMIN,
            ).exists()
        )
        retrieve_subscription_mock.assert_called_once_with('sub_new_123')
        apply_subscription_payload_mock.assert_called_once()
