# Cognito Hosted UI testing (dev)

## Deploy from `terraform/envs/dev`

```bash
terraform init
terraform plan
terraform apply
```

## Test OAuth2 in Postman (Authorization Code + PKCE)

Use Terraform outputs for the Cognito domain/client details:

- Grant Type: **Authorization Code (With PKCE)**
- Auth URL: `{cognito_hosted_ui_base_url}/oauth2/authorize`
- Access Token URL: `{cognito_hosted_ui_base_url}/oauth2/token`
- Client ID: `{cognito_user_pool_client_id}`
- Callback URL: `https://oauth.pstmn.io/v1/callback`
- Scope: `openid email profile`

When the browser opens Cognito Hosted UI:

1. Sign up with email and password.
2. Enter the verification **code** received by email.
3. Sign in and complete consent.
4. Postman receives authorization code and exchanges it for tokens.

## Calling Django APIs with Cognito tokens

Use the access token in API requests:

```http
Authorization: Bearer <access_token>
```

Django environment variables needed for Cognito JWT validation:

- `COGNITO_REGION`
- `COGNITO_USER_POOL_ID`
- `COGNITO_APP_CLIENT_ID`
- `COGNITO_ISSUER`

## Notes

- This module supports configurable MFA (`OFF`, `OPTIONAL`, `ON`) with TOTP (`software_token_mfa_configuration`).
- Optional `ses_source_arn` enables Cognito developer email sending via SES.
- Email OTP MFA is not configured; it may require SES setup and additional AWS prerequisites.
