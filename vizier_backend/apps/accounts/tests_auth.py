from unittest.mock import Mock, patch

from datetime import timedelta
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.auth import CognitoJWTAuthentication
from apps.accounts.models import User, UserNotice, UserSubscription


@override_settings(COGNITO_AUDIENCE='test-client-id')
class CognitoAudienceValidationTest(SimpleTestCase):
    def test_access_token_accepts_client_id(self):
        claims = {
            'token_use': 'access',
            'client_id': 'test-client-id',
        }

        CognitoJWTAuthentication._validate_cognito_audience(claims)

    def test_access_token_rejects_wrong_client_id(self):
        claims = {
            'token_use': 'access',
            'client_id': 'other-client-id',
        }

        with self.assertRaises(AuthenticationFailed):
            CognitoJWTAuthentication._validate_cognito_audience(claims)

    def test_id_token_accepts_audience(self):
        claims = {
            'token_use': 'id',
            'aud': 'test-client-id',
        }

        CognitoJWTAuthentication._validate_cognito_audience(claims)

    def test_id_token_rejects_wrong_audience(self):
        claims = {
            'token_use': 'id',
            'aud': 'other-client-id',
        }

        with self.assertRaises(AuthenticationFailed):
            CognitoJWTAuthentication._validate_cognito_audience(claims)


class CognitoClaimsExtractionTest(SimpleTestCase):
    def test_extracts_email_directly(self):
        claims = {'email': 'dev@vizier.com'}
        self.assertEqual(
            CognitoJWTAuthentication._extract_email_from_claims(claims),
            'dev@vizier.com',
        )

    def test_extracts_email_from_cognito_username(self):
        claims = {'cognito:username': 'dev@vizier.com'}
        self.assertEqual(
            CognitoJWTAuthentication._extract_email_from_claims(claims),
            'dev@vizier.com',
        )

    def test_returns_none_without_email_like_claim(self):
        claims = {'cognito:username': 'abc123'}
        self.assertIsNone(CognitoJWTAuthentication._extract_email_from_claims(claims))


class CognitoIdentityFallbackTest(SimpleTestCase):
    @override_settings(COGNITO_USERINFO_URL='https://example.com/oauth2/userInfo')
    @patch('apps.accounts.auth.requests.get')
    def test_fetches_email_from_userinfo(self, get_mock):
        get_mock.return_value = Mock(
            status_code=200,
            json=lambda: {'email': 'dev@vizier.com'},
            raise_for_status=lambda: None,
        )

        result = CognitoJWTAuthentication._fetch_email_from_userinfo('access-token')

        self.assertEqual(result, 'dev@vizier.com')
        get_mock.assert_called_once()

    @override_settings(COGNITO_USERINFO_URL=None)
    def test_userinfo_returns_none_when_not_configured(self):
        self.assertIsNone(CognitoJWTAuthentication._fetch_email_from_userinfo('access-token'))

    def test_builds_fallback_email_from_sub(self):
        self.assertEqual(
            CognitoJWTAuthentication._build_fallback_email('abc-123'),
            'abc-123@cognito.local',
        )


class CognitoDevelopmentAuthModeTest(SimpleTestCase):
    @override_settings(
        DEBUG=True,
        DEVELOPMENT_MODE=True,
        ALLOW_INSECURE_DEV_AUTH_FALLBACK=True,
        COGNITO_USER_POOL_ID='',
    )
    def test_uses_development_auth_without_pool_id(self):
        self.assertTrue(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(
        DEBUG=True,
        DEVELOPMENT_MODE=True,
        ALLOW_INSECURE_DEV_AUTH_FALLBACK=True,
        COGNITO_USER_POOL_ID='us-east-1_xxxxxxxxx',
    )
    def test_uses_development_auth_for_placeholder_pool_id(self):
        self.assertTrue(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(
        DEBUG=True,
        DEVELOPMENT_MODE=True,
        ALLOW_INSECURE_DEV_AUTH_FALLBACK=True,
        COGNITO_USER_POOL_ID='us-east-1_realpool',
    )
    def test_disables_development_auth_when_pool_id_is_real(self):
        self.assertFalse(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(
        DEBUG=True,
        DEVELOPMENT_MODE=False,
        ALLOW_INSECURE_DEV_AUTH_FALLBACK=True,
        COGNITO_USER_POOL_ID='',
    )
    def test_disables_development_auth_when_flag_is_false(self):
        self.assertFalse(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(
        DEBUG=True,
        DEVELOPMENT_MODE=True,
        ALLOW_INSECURE_DEV_AUTH_FALLBACK=False,
        COGNITO_USER_POOL_ID='',
    )
    def test_disables_development_auth_when_insecure_fallback_is_disabled(self):
        self.assertFalse(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(
        DEBUG=False,
        DEVELOPMENT_MODE=True,
        ALLOW_INSECURE_DEV_AUTH_FALLBACK=True,
        COGNITO_USER_POOL_ID='',
    )
    def test_disables_development_auth_when_debug_is_false(self):
        self.assertFalse(CognitoJWTAuthentication._should_use_development_auth())


@override_settings(
    COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test',
    COGNITO_AUDIENCE='test-client-id',
    COGNITO_JWT_LEEWAY_SECONDS=60,
)
class CognitoTokenValidationTest(SimpleTestCase):
    @patch('apps.accounts.auth.CognitoJWTAuthentication._validate_cognito_audience')
    @patch('apps.accounts.auth.jwt.decode')
    @patch('apps.accounts.auth.jwt.algorithms.RSAAlgorithm.from_jwk')
    @patch('apps.accounts.auth.jwt.get_unverified_header')
    @patch('apps.accounts.auth.CognitoJWTAuthentication._get_jwks')
    def test_validate_token_passes_configured_leeway(
        self,
        get_jwks_mock,
        get_header_mock,
        from_jwk_mock,
        decode_mock,
        validate_audience_mock,
    ):
        get_jwks_mock.return_value = {
            'keys': [{'kid': 'key-1', 'kty': 'RSA', 'e': 'AQAB', 'n': 'abc'}]
        }
        get_header_mock.return_value = {'kid': 'key-1'}
        from_jwk_mock.return_value = 'rsa-key'
        decode_mock.return_value = {'sub': 'user-1', 'token_use': 'access', 'client_id': 'test-client-id'}

        claims = CognitoJWTAuthentication._validate_token('jwt-token')

        self.assertEqual(claims['sub'], 'user-1')
        decode_mock.assert_called_once_with(
            'jwt-token',
            'rsa-key',
            algorithms=['RS256'],
            issuer='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test',
            leeway=60,
            options={'verify_aud': False},
        )
        validate_audience_mock.assert_called_once_with(claims)


@override_settings(
    COGNITO_CLIENT_ID='test-client-id',
    COGNITO_TOKEN_URL='https://example.auth.us-east-1.amazoncognito.com/oauth2/token',
    SECURE_SSL_REDIRECT=False,
)
class CognitoCallbackViewTest(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_callback_requires_code(self):
        response = self.client.get('/api/auth/cognito/callback/')
        self.assertEqual(response.status_code, 400)

    @patch('apps.accounts.views.requests.post')
    def test_callback_exchanges_code_when_verifier_is_sent(self, post_mock):
        post_mock.return_value = Mock(
            status_code=200,
            json=lambda: {'access_token': 'a', 'id_token': 'i'},
            raise_for_status=lambda: None,
        )

        response = self.client.get(
            '/api/auth/cognito/callback/',
            {
                'code': 'abc',
                'redirect_uri': 'https://oauth.pstmn.io/v1/callback',
                'code_verifier': 'verifier',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['tokens']['access_token'], 'a')
        post_mock.assert_called_once()


@override_settings(
    DEV_MOCK_AUTH_ENABLED=True,
    COGNITO_USER_POOL_ID='us-east-1_realpool',
    COGNITO_ISSUER='https://cognito-idp.us-east-1.amazonaws.com/us-east-1_realpool',
    COGNITO_AUDIENCE='real-client-id',
    COGNITO_JWKS_URL='https://example.com/jwks.json',
)
class DevMockAuthEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_returns_access_token_and_authenticates(self):
        signup_response = self.client.post(
            '/api/auth/dev/signup/',
            {
                'email': 'dev-mock@example.com',
                'password': 'dev-password-123',
                'first_name': 'Dev',
                'last_name': 'Mock',
            },
            format='json',
        )

        self.assertEqual(signup_response.status_code, 201)
        token = signup_response.data['access_token']
        self.assertTrue(token.startswith('devmock.'))

        me_response = self.client.get(
            '/api/auth/users/me/',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data['email'], 'dev-mock@example.com')

    def test_login_returns_access_token_for_existing_dev_user(self):
        signup_response = self.client.post(
            '/api/auth/dev/signup/',
            {
                'email': 'existing-dev@example.com',
                'password': 'dev-password-123',
            },
            format='json',
        )
        self.assertEqual(signup_response.status_code, 201)

        login_response = self.client.post(
            '/api/auth/dev/login/',
            {
                'email': 'existing-dev@example.com',
                'password': 'dev-password-123',
            },
            format='json',
        )

        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.data['access_token'].startswith('devmock.'))

    def test_login_rejects_invalid_password(self):
        signup_response = self.client.post(
            '/api/auth/dev/signup/',
            {
                'email': 'wrong-pass@example.com',
                'password': 'dev-password-123',
            },
            format='json',
        )
        self.assertEqual(signup_response.status_code, 201)

        login_response = self.client.post(
            '/api/auth/dev/login/',
            {
                'email': 'wrong-pass@example.com',
                'password': 'invalid-password',
            },
            format='json',
        )

        self.assertEqual(login_response.status_code, 400)


@override_settings(DEV_MOCK_AUTH_ENABLED=False)
class DevMockAuthDisabledTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_signup_is_blocked_when_disabled(self):
        response = self.client.post(
            '/api/auth/dev/signup/',
            {'email': 'blocked@example.com', 'password': 'dev-password-123'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_login_is_blocked_when_disabled(self):
        response = self.client.post(
            '/api/auth/dev/login/',
            {'email': 'blocked@example.com', 'password': 'dev-password-123'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)


class UserNoticesApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='notice-user@example.com',
            cognito_sub='notice-user-sub',
            role='INDIVIDUAL',
        )
        self.client.force_authenticate(user=self.user)

    def test_me_exposes_effective_role_and_pending_notices(self):
        notice = UserNotice.objects.create(
            user=self.user,
            type=UserNotice.TYPE_CLINIC_REMOVED,
            title='Aviso',
            message='Você foi desligado',
            payload={'clinic_name': 'Demo'},
        )

        response = self.client.get('/api/auth/users/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['effective_role'], 'individual')
        self.assertEqual(len(response.data['notices']), 1)
        self.assertEqual(response.data['notices'][0]['id'], str(notice.id))

    def test_acknowledge_notices_marks_selected_rows(self):
        first_notice = UserNotice.objects.create(
            user=self.user,
            type=UserNotice.TYPE_CLINIC_REMOVED,
            title='Aviso 1',
            message='Primeiro',
        )
        second_notice = UserNotice.objects.create(
            user=self.user,
            type=UserNotice.TYPE_CLINIC_REMOVED,
            title='Aviso 2',
            message='Segundo',
        )

        response = self.client.post(
            '/api/auth/users/acknowledge_notices/',
            {'notice_ids': [str(first_notice.id)]},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['acknowledged'], 1)

        first_notice.refresh_from_db()
        second_notice.refresh_from_db()
        self.assertIsNotNone(first_notice.acknowledged_at)
        self.assertIsNone(second_notice.acknowledged_at)

    def test_acknowledge_notices_without_ids_marks_all_pending(self):
        UserNotice.objects.create(
            user=self.user,
            type=UserNotice.TYPE_CLINIC_REMOVED,
            title='Aviso 1',
            message='Primeiro',
        )
        UserNotice.objects.create(
            user=self.user,
            type=UserNotice.TYPE_CLINIC_REMOVED,
            title='Aviso 2',
            message='Segundo',
        )

        response = self.client.post(
            '/api/auth/users/acknowledge_notices/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['acknowledged'], 2)
        self.assertEqual(self.user.notices.filter(acknowledged_at__isnull=True).count(), 0)


class OffboardingApiTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='offboarding-user@example.com',
            cognito_sub='offboarding-user-sub',
            role='INDIVIDUAL',
        )
        self.user.set_password('offboarding-pass-123')
        self.user.save(update_fields=['password', 'updated_at'])
        self.client.force_authenticate(user=self.user)

    @patch('apps.accounts.offboarding.retrieve_individual_subscription')
    def test_offboarding_status_blocks_active_individual_subscription(
        self,
        retrieve_individual_subscription_mock,
    ):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_subscription_id='sub_offboarding_active',
            current_period_end=timezone.now() + timedelta(days=20),
        )
        retrieve_individual_subscription_mock.return_value = {
            'id': 'sub_offboarding_active',
            'status': 'active',
            'current_period_end': int((timezone.now() + timedelta(days=20)).timestamp()),
        }

        response = self.client.get('/api/auth/users/offboarding_status/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['can_delete_account'])
        blocker_codes = {item['code'] for item in response.data['blockers']}
        self.assertIn('INDIVIDUAL_SUBSCRIPTION_ACTIVE', blocker_codes)

    def test_delete_account_requires_confirmation_text(self):
        response = self.client.post(
            '/api/auth/users/delete_account/',
            {'confirm_text': 'WRONG', 'current_password': 'offboarding-pass-123'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    @patch('apps.accounts.offboarding.retrieve_individual_subscription')
    def test_delete_account_blocks_while_subscription_is_active(
        self,
        retrieve_individual_subscription_mock,
    ):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_subscription_id='sub_delete_blocked',
            current_period_end=timezone.now() + timedelta(days=5),
        )
        retrieve_individual_subscription_mock.return_value = {
            'id': 'sub_delete_blocked',
            'status': 'active',
            'current_period_end': int((timezone.now() + timedelta(days=5)).timestamp()),
        }

        response = self.client.post(
            '/api/auth/users/delete_account/',
            {'confirm_text': 'EXCLUIR', 'current_password': 'offboarding-pass-123'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.user.refresh_from_db()
        self.assertEqual(self.user.account_lifecycle_status, User.ACCOUNT_LIFECYCLE_ACTIVE)

    def test_delete_account_soft_deletes_and_anonymizes_user(self):
        response = self.client.post(
            '/api/auth/users/delete_account/',
            {'confirm_text': 'EXCLUIR', 'current_password': 'offboarding-pass-123'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.account_lifecycle_status, User.ACCOUNT_LIFECYCLE_DELETED)
        self.assertTrue(self.user.email.startswith(f'deleted+{self.user.id}@deleted.local'))
        self.assertEqual(self.user.first_name, '')
        self.assertEqual(self.user.last_name, '')
        self.assertIsNotNone(self.user.deleted_at)
        self.assertIsNotNone(self.user.anonymized_at)


class CognitoDeletedUserAuthTest(TestCase):
    @patch('apps.accounts.auth.CognitoJWTAuthentication._validate_token')
    @patch('apps.accounts.auth.CognitoJWTAuthentication._authenticate_dev_mock_token')
    @patch('apps.accounts.auth.CognitoJWTAuthentication._should_use_development_auth')
    def test_authentication_rejects_deleted_user(
        self,
        should_use_development_auth_mock,
        authenticate_dev_mock_token_mock,
        validate_token_mock,
    ):
        should_use_development_auth_mock.return_value = False
        authenticate_dev_mock_token_mock.return_value = None
        validate_token_mock.return_value = {
            'sub': 'deleted-user-sub',
            'email': 'deleted-user@example.com',
            'token_use': 'access',
            'client_id': 'test-client-id',
        }

        deleted_user = User.objects.create_user(
            email='deleted-user@example.com',
            cognito_sub='deleted-user-sub',
            role='INDIVIDUAL',
        )
        deleted_user.account_lifecycle_status = User.ACCOUNT_LIFECYCLE_DELETED
        deleted_user.is_active = False
        deleted_user.save(update_fields=['account_lifecycle_status', 'is_active', 'updated_at'])

        auth = CognitoJWTAuthentication()
        with self.assertRaises(AuthenticationFailed):
            auth.authenticate_credentials('jwt-token')


@override_settings(DEFAULT_FROM_EMAIL='no-reply@vizier.com')
class ConsultationRequestViewTest(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/auth/consultation-request/'

    @patch('apps.accounts.emails.send_mail')
    def test_valid_payload_returns_201_and_calls_send_mail(self, send_mail_mock):
        response = self.client.post(
            self.url,
            {
                'first_name': 'Ana',
                'last_name': 'Silva',
                'company_name': 'Hospital Central',
                'job_title': 'Radiologista',
                'email': 'ana.silva@example.com',
                'country': 'Brasil',
                'message': 'Gostaria de agendar uma apresentação da plataforma.',
                'discovery_source': 'Indicação',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['detail'], 'Solicitação enviada com sucesso.')
        send_mail_mock.assert_called_once()
        self.assertEqual(
            send_mail_mock.call_args.kwargs['recipient_list'],
            ['vizier.med@gmail.com'],
        )

    def test_missing_email_returns_400(self):
        response = self.client.post(
            self.url,
            {
                'country': 'Brasil',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('email', response.data)

    def test_missing_country_returns_400(self):
        response = self.client.post(
            self.url,
            {
                'email': 'lead@example.com',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('country', response.data)

    @patch('apps.accounts.emails.send_mail')
    def test_optional_fields_accept_blank_values(self, send_mail_mock):
        response = self.client.post(
            self.url,
            {
                'first_name': '',
                'last_name': '',
                'company_name': '',
                'job_title': '',
                'email': 'lead@example.com',
                'country': 'Portugal',
                'message': '',
                'discovery_source': '',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        send_mail_mock.assert_called_once()

    @patch('apps.accounts.emails.send_mail', side_effect=RuntimeError('smtp down'))
    def test_email_send_failure_returns_500(self, _send_mail_mock):
        response = self.client.post(
            self.url,
            {
                'email': 'lead@example.com',
                'country': 'Brasil',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data['error'], 'Failed to send consultation request')
