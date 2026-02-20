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
