const fallbackOrigin =
  typeof window !== "undefined"
    ? window.location.origin
    : "http://localhost:3000";

function parseBoolean(value: string | undefined, defaultValue = false) {
  if (value == null || value === "") {
    return defaultValue;
  }

  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function parseNumber(value: string | undefined, defaultValue: number) {
  if (value == null || value === "") {
    return defaultValue;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

function normalizeEndpointForSecureFrontend(
  endpoint: string,
  fallbackPath: string,
) {
  if (typeof window === "undefined" || window.location.protocol !== "https:") {
    return endpoint;
  }

  if (!endpoint.startsWith("http://")) {
    return endpoint;
  }

  try {
    const parsed = new URL(endpoint);
    return `${window.location.origin}${parsed.pathname || fallbackPath}${parsed.search || ""}`;
  } catch {
    return `${window.location.origin}${fallbackPath}`;
  }
}

const configuredApiBaseUrl = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
);

const shouldUseSameOriginApiProxy =
  typeof window !== "undefined" &&
  window.location.protocol === "https:" &&
  configuredApiBaseUrl.startsWith("http://");

const apiBaseUrl = shouldUseSameOriginApiProxy
  ? trimTrailingSlash(window.location.origin)
  : configuredApiBaseUrl;

const redirectUri =
  import.meta.env.VITE_COGNITO_REDIRECT_URI ||
  `${fallbackOrigin}/auth/callback`;

const logoutUri =
  import.meta.env.VITE_COGNITO_LOGOUT_URI || `${fallbackOrigin}/login`;

const defaultBillingCheckoutEndpoint = `${apiBaseUrl}/api/auth/billing/checkout/`;
const defaultBillingPortalEndpoint = `${apiBaseUrl}/api/auth/billing/portal/`;

const billingCheckoutEndpoint = normalizeEndpointForSecureFrontend(
  import.meta.env.VITE_BILLING_CHECKOUT_ENDPOINT || defaultBillingCheckoutEndpoint,
  "/api/auth/billing/checkout/",
);

const billingPortalEndpoint = normalizeEndpointForSecureFrontend(
  import.meta.env.VITE_BILLING_PORTAL_ENDPOINT || defaultBillingPortalEndpoint,
  "/api/auth/billing/portal/",
);

export const env = {
  apiBaseUrl,
  apiTimeoutMs: Math.max(
    1_000,
    parseNumber(import.meta.env.VITE_API_TIMEOUT_MS, 15_000),
  ),
  cognitoRegion: import.meta.env.VITE_COGNITO_REGION || "",
  cognitoUserPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID || "",
  cognitoClientId: import.meta.env.VITE_COGNITO_CLIENT_ID || "",
  cognitoDomain: trimTrailingSlash(import.meta.env.VITE_COGNITO_DOMAIN || ""),
  cognitoRedirectUri: redirectUri,
  cognitoLogoutUri: logoutUri,
  stripePublishableKey: import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || "",
  enableBilling: parseBoolean(import.meta.env.VITE_ENABLE_BILLING, false),
  billingCheckoutEndpoint,
  billingPortalEndpoint,
  enableDevMockAuth: parseBoolean(
    import.meta.env.VITE_ENABLE_DEV_MOCK_AUTH,
    import.meta.env.DEV,
  ),
  useAsyncS3Upload: parseBoolean(
    import.meta.env.VITE_USE_ASYNC_S3_UPLOAD,
    false,
  ),
};

export const isCognitoConfigured = Boolean(
  env.cognitoClientId && env.cognitoDomain && env.cognitoRedirectUri,
);

export const isBillingConfigured = Boolean(
  env.enableBilling && env.billingCheckoutEndpoint && env.billingPortalEndpoint,
);
