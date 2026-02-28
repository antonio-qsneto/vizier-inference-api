const fallbackOrigin =
  typeof window !== "undefined" ? window.location.origin : "http://localhost:3000";

function parseBoolean(value: string | undefined, defaultValue = false) {
  if (value == null || value === "") {
    return defaultValue;
  }

  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

const apiBaseUrl = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
);

const redirectUri =
  import.meta.env.VITE_COGNITO_REDIRECT_URI || `${fallbackOrigin}/auth/callback`;

const logoutUri =
  import.meta.env.VITE_COGNITO_LOGOUT_URI || `${fallbackOrigin}/login`;

export const env = {
  apiBaseUrl,
  cognitoRegion: import.meta.env.VITE_COGNITO_REGION || "",
  cognitoUserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || "",
  cognitoClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || "",
  cognitoDomain: trimTrailingSlash(import.meta.env.VITE_COGNITO_DOMAIN || ""),
  cognitoRedirectUri: redirectUri,
  cognitoLogoutUri: logoutUri,
  stripePublishableKey: import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || "",
  enableBilling: parseBoolean(import.meta.env.VITE_ENABLE_BILLING, false),
  billingCheckoutEndpoint:
    import.meta.env.VITE_BILLING_CHECKOUT_ENDPOINT || "",
};

export const isCognitoConfigured = Boolean(
  env.cognitoClientId && env.cognitoDomain && env.cognitoRedirectUri,
);

export const isBillingConfigured = Boolean(
  env.enableBilling &&
    env.stripePublishableKey &&
    env.billingCheckoutEndpoint,
);
