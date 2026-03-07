const AUTH_SESSION_KEY = "vizier.auth.session.v1";
const AUTH_NOTICE_KEY = "vizier.auth.notice.v1";

export type AuthProvider = "cognito" | "dev_mock" | "local_fallback";

export interface AuthTokens {
  accessToken: string;
  idToken?: string;
  refreshToken?: string;
  expiresAt: number;
}

export interface AuthSession {
  provider: AuthProvider;
  tokens: AuthTokens;
}

export interface TokenExchangePayload {
  access_token: string;
  id_token?: string;
  refresh_token?: string;
  expires_in?: number;
}

export function createSessionFromTokens(
  tokens: TokenExchangePayload,
  provider: AuthProvider = "cognito",
): AuthSession {
  return {
    provider,
    tokens: {
      accessToken: tokens.access_token,
      idToken: tokens.id_token,
      refreshToken: tokens.refresh_token,
      expiresAt: Date.now() + (tokens.expires_in ?? 3600) * 1000,
    },
  };
}

export function createDevelopmentSession(): AuthSession {
  return {
    provider: "local_fallback",
    tokens: {
      accessToken: "dev-token",
      expiresAt: Date.now() + 12 * 60 * 60 * 1000,
    },
  };
}

export function saveAuthSession(session: AuthSession) {
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

export function loadAuthSession(): AuthSession | null {
  const rawValue = sessionStorage.getItem(AUTH_SESSION_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<AuthSession>;
    if (!parsed.tokens?.accessToken || !parsed.tokens.expiresAt) {
      return null;
    }

    const provider: AuthProvider =
      parsed.provider === "dev_mock" || parsed.provider === "local_fallback"
        ? parsed.provider
        : "cognito";

    return {
      provider,
      tokens: parsed.tokens,
    };
  } catch {
    return null;
  }
}

export function clearAuthSession() {
  sessionStorage.removeItem(AUTH_SESSION_KEY);
}

export function isSessionUsable(session: AuthSession | null) {
  if (!session) {
    return false;
  }

  return session.tokens.expiresAt > Date.now() + 30_000;
}

export function saveAuthNotice(message: string) {
  sessionStorage.setItem(AUTH_NOTICE_KEY, message);
}

export function consumeAuthNotice() {
  const message = sessionStorage.getItem(AUTH_NOTICE_KEY);
  if (!message) {
    return null;
  }

  sessionStorage.removeItem(AUTH_NOTICE_KEY);
  return message;
}
