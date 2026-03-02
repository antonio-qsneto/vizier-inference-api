from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.auth import CognitoJWTAuthentication


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
    @override_settings(DEVELOPMENT_MODE=True, COGNITO_USER_POOL_ID='')
    def test_uses_development_auth_without_pool_id(self):
        self.assertTrue(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(DEVELOPMENT_MODE=True, COGNITO_USER_POOL_ID='us-east-1_xxxxxxxxx')
    def test_uses_development_auth_for_placeholder_pool_id(self):
        self.assertTrue(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(DEVELOPMENT_MODE=True, COGNITO_USER_POOL_ID='us-east-1_realpool')
    def test_disables_development_auth_when_pool_id_is_real(self):
        self.assertFalse(CognitoJWTAuthentication._should_use_development_auth())

    @override_settings(DEVELOPMENT_MODE=False, COGNITO_USER_POOL_ID='')
    def test_disables_development_auth_when_flag_is_false(self):
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
