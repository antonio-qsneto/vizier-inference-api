from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from datetime import timedelta

from apps.accounts.models import User
from apps.tenants.models import Clinic, DoctorInvitation


class ClinicCreateApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='clinic-admin@example.com',
            cognito_sub='clinic-admin-sub',
            role='INDIVIDUAL',
        )
        self.client.force_authenticate(user=self.user)

    def test_create_clinic_sets_owner_and_user_membership(self):
        response = self.client.post(
            '/api/clinics/clinics/',
            {'name': 'My Clinic', 'cnpj': '12345678000199'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)

        clinic = Clinic.objects.get(id=response.data['id'])
        self.user.refresh_from_db()

        self.assertEqual(clinic.owner, self.user)
        self.assertEqual(self.user.clinic, clinic)
        self.assertEqual(self.user.role, 'CLINIC_ADMIN')

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
