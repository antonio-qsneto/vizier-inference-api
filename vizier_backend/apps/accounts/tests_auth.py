from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed

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
