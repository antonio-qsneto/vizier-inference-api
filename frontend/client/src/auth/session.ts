const AUTH_SESSION_KEY = "vizier.auth.session.v1";

export interface AuthTokens {
  accessToken: string;
  idToken?: string;
  refreshToken?: string;
  expiresAt: number;
}

export interface AuthSession {
  tokens: AuthTokens;
}

export interface TokenExchangePayload {
  access_token: string;
  id_token?: string;
  refresh_token?: string;
  expires_in?: number;
}

export function createSessionFromTokens(tokens: TokenExchangePayload): AuthSession {
  return {
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
    tokens: {
      accessToken: "dev-token",
      expiresAt: Date.now() + 12 * 60 * 60 * 1000,
    },
  };
}

export function saveAuthSession(session: AuthSession) {
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

export function loadAuthSession() {
  const rawValue = sessionStorage.getItem(AUTH_SESSION_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as AuthSession;
    if (!parsed.tokens?.accessToken) {
      return null;
    }
    return parsed;
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
