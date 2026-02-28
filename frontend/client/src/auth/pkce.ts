import { env } from "@/env";

export type AuthIntent = "login" | "signup";

const PKCE_STORAGE_KEY = "vizier.auth.pkce.v1";

export interface PendingPkceState {
  state: string;
  codeVerifier: string;
  intent: AuthIntent;
  createdAt: number;
}

function base64UrlEncode(bytes: Uint8Array) {
  const binary = Array.from(bytes, (value) => String.fromCharCode(value)).join("");
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function randomString(length: number) {
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return base64UrlEncode(bytes);
}

async function createCodeChallenge(codeVerifier: string) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(codeVerifier),
  );
  return base64UrlEncode(new Uint8Array(digest));
}

export async function createHostedUiRequest(intent: AuthIntent) {
  const state = randomString(24);
  const codeVerifier = randomString(64);
  const codeChallenge = await createCodeChallenge(codeVerifier);

  const params = new URLSearchParams({
    response_type: "code",
    client_id: env.cognitoClientId,
    redirect_uri: env.cognitoRedirectUri,
    scope: "openid email profile",
    state,
    code_challenge_method: "S256",
    code_challenge: codeChallenge,
  });

  if (intent === "signup") {
    params.set("signup", "true");
  }

  return {
    url: `${env.cognitoDomain}/login?${params.toString()}`,
    pendingState: {
      state,
      codeVerifier,
      intent,
      createdAt: Date.now(),
    } satisfies PendingPkceState,
  };
}

export function savePendingPkce(state: PendingPkceState) {
  sessionStorage.setItem(PKCE_STORAGE_KEY, JSON.stringify(state));
}

export function loadPendingPkce() {
  const rawValue = sessionStorage.getItem(PKCE_STORAGE_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as PendingPkceState;
    if (!parsed.state || !parsed.codeVerifier) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearPendingPkce() {
  sessionStorage.removeItem(PKCE_STORAGE_KEY);
}

export function buildCognitoLogoutUrl() {
  const params = new URLSearchParams({
    client_id: env.cognitoClientId,
    logout_uri: env.cognitoLogoutUri,
  });

  return `${env.cognitoDomain}/logout?${params.toString()}`;
}
