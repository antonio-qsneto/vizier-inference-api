import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  devMockLogin,
  devMockSignup,
  fetchCurrentUser,
  type DevMockLoginPayload,
  type DevMockSignupPayload,
} from "@/api/services";
import { ApiError } from "@/api/client";
import { env, isCognitoConfigured } from "@/env";
import {
  AuthSession,
  TokenExchangePayload,
  clearAuthSession,
  createDevelopmentSession,
  createSessionFromTokens,
  isSessionUsable,
  loadAuthSession,
  saveAuthNotice,
  saveAuthSession,
} from "@/auth/session";
import {
  AuthIntent,
  buildCognitoLogoutUrl,
  clearPendingPkce,
  createHostedUiRequest,
  loadPendingPkce,
  savePendingPkce,
} from "@/auth/pkce";
import type { UserProfile } from "@/types/api";

type AuthStatus = "loading" | "authenticated" | "guest";

interface AuthContextValue {
  status: AuthStatus;
  session: AuthSession | null;
  user: UserProfile | null;
  error: string | null;
  accessToken: string | null;
  isCognitoConfigured: boolean;
  isDevMockAuthEnabled: boolean;
  signIn: (intent?: AuthIntent) => Promise<void>;
  signInDevMock: (payload: DevMockLoginPayload) => Promise<void>;
  signUpDevMock: (payload: DevMockSignupPayload) => Promise<void>;
  completeHostedUiLogin: (
    searchParams: URLSearchParams,
  ) => Promise<"authenticated" | "signup_completed">;
  logout: (remote?: boolean) => void;
  refreshProfile: () => Promise<UserProfile | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const SIGNUP_SUCCESS_NOTICE = "Cadastro confirmado. Faça login para continuar.";

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  timeoutMs = env.apiTimeoutMs,
) {
  const controller = new AbortController();
  const timeoutHandle = window.setTimeout(() => controller.abort(), timeoutMs);
  const upstreamSignal = init?.signal;
  const onUpstreamAbort = () => controller.abort();

  if (upstreamSignal) {
    if (upstreamSignal.aborted) {
      controller.abort();
    } else {
      upstreamSignal.addEventListener("abort", onUpstreamAbort, { once: true });
    }
  }

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Timeout na autenticação após ${timeoutMs}ms`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutHandle);
    if (upstreamSignal) {
      upstreamSignal.removeEventListener("abort", onUpstreamAbort);
    }
  }
}

async function exchangeCodeWithBackend(
  code: string,
  state: string,
  codeVerifier: string,
) {
  const params = new URLSearchParams({
    code,
    state,
    redirect_uri: env.cognitoRedirectUri,
    code_verifier: codeVerifier,
  });

  const response = await fetchWithTimeout(
    `${env.apiBaseUrl}/api/auth/cognito/callback/?${params.toString()}`,
    undefined,
    4_000,
  );
  const payload = (await response.json().catch(() => null)) as {
    tokens?: TokenExchangePayload;
    error?: string;
    details?: string;
  } | null;

  if (!response.ok || !payload?.tokens?.access_token) {
    throw new Error(
      payload?.details ||
        payload?.error ||
        "Token exchange with backend failed",
    );
  }

  return payload.tokens;
}

async function exchangeCodeWithCognito(code: string, codeVerifier: string) {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: env.cognitoClientId,
    code,
    redirect_uri: env.cognitoRedirectUri,
    code_verifier: codeVerifier,
  });

  const response = await fetchWithTimeout(`${env.cognitoDomain}/oauth2/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  const payload = (await response.json().catch(() => null)) as
    | TokenExchangePayload
    | { error?: string; error_description?: string }
    | null;

  if (!response.ok || !payload || !("access_token" in payload)) {
    const details =
      payload && "error_description" in payload
        ? payload.error_description
        : "Token exchange with Cognito failed";
    throw new Error(details);
  }

  return payload;
}

function resolveAuthErrorMessage(error: unknown) {
  const isMixedContentScenario =
    typeof window !== "undefined" &&
    window.location.protocol === "https:" &&
    env.apiBaseUrl.startsWith("http://");

  if (isMixedContentScenario) {
    return (
      `O frontend está em HTTPS (${window.location.origin}) mas a API está em HTTP (${env.apiBaseUrl}). ` +
      "O navegador bloqueia essa chamada (mixed content). Exponha a API em HTTPS e atualize VITE_API_BASE_URL."
    );
  }

  if (
    error instanceof TypeError &&
    /failed to fetch/i.test(error.message)
  ) {
    const frontendOrigin =
      typeof window !== "undefined" ? window.location.origin : "unknown origin";
    return (
      `Falha de conexão com ${env.apiBaseUrl}. ` +
      `Verifique se o backend está rodando e se CORS_ALLOWED_ORIGINS inclui ${frontendOrigin}.`
    );
  }

  if (error instanceof ApiError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Authentication failed";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [user, setUser] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applySession = useCallback(async (nextSession: AuthSession) => {
    saveAuthSession(nextSession);
    setSession(nextSession);

    try {
      const profile = await fetchCurrentUser(nextSession.tokens.accessToken);
      setUser(profile);
      setError(null);
      setStatus("authenticated");
      return profile;
    } catch (requestError) {
      clearAuthSession();
      setSession(null);
      setUser(null);
      setStatus("guest");
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
      return null;
    }
  }, []);

  useEffect(() => {
    const existingSession = loadAuthSession();
    if (!isSessionUsable(existingSession)) {
      clearAuthSession();
      setStatus("guest");
      return;
    }

    if (existingSession) {
      void applySession(existingSession);
    }
  }, [applySession]);

  const signIn = useCallback(
    async (intent: AuthIntent = "login") => {
      setError(null);

      if (!isCognitoConfigured) {
        await applySession(createDevelopmentSession());
        return;
      }

      const request = await createHostedUiRequest(intent);
      savePendingPkce(request.pendingState);
      window.location.assign(request.url);
    },
    [applySession],
  );

  const signInDevMock = useCallback(
    async (payload: DevMockLoginPayload) => {
      if (!env.enableDevMockAuth) {
        throw new Error(
          "Development mock auth is disabled in frontend config.",
        );
      }

      setError(null);
      try {
        const tokens = await devMockLogin(payload);
        await applySession(createSessionFromTokens(tokens, "dev_mock"));
      } catch (requestError) {
        setError(resolveAuthErrorMessage(requestError));
        throw requestError;
      }
    },
    [applySession],
  );

  const signUpDevMock = useCallback(
    async (payload: DevMockSignupPayload) => {
      if (!env.enableDevMockAuth) {
        throw new Error(
          "Development mock auth is disabled in frontend config.",
        );
      }

      setError(null);
      try {
        const tokens = await devMockSignup(payload);
        await applySession(createSessionFromTokens(tokens, "dev_mock"));
      } catch (requestError) {
        setError(resolveAuthErrorMessage(requestError));
        throw requestError;
      }
    },
    [applySession],
  );

  const completeHostedUiLogin = useCallback(
    async (searchParams: URLSearchParams) => {
      const returnedState = searchParams.get("state") || "";
      const code = searchParams.get("code");
      const errorValue = searchParams.get("error");
      const errorDescription = searchParams.get("error_description");

      if (errorValue) {
        throw new Error(errorDescription || errorValue);
      }

      if (!code) {
        throw new Error("Missing authorization code");
      }

      const pendingState = loadPendingPkce();
      if (!pendingState) {
        throw new Error("Authentication session not found. Start login again.");
      }

      if (pendingState.state !== returnedState) {
        throw new Error("Invalid authentication state");
      }

      if (pendingState.intent === "signup") {
        clearPendingPkce();
        clearAuthSession();
        saveAuthNotice(SIGNUP_SUCCESS_NOTICE);
        setSession(null);
        setUser(null);
        setError(null);
        setStatus("guest");
        return "signup_completed";
      }

      try {
        const tokens = await exchangeCodeWithBackend(
          code,
          returnedState,
          pendingState.codeVerifier,
        );
        clearPendingPkce();
        await applySession(createSessionFromTokens(tokens));
        return "authenticated";
      } catch {
        const tokens = await exchangeCodeWithCognito(
          code,
          pendingState.codeVerifier,
        );
        clearPendingPkce();
        await applySession(createSessionFromTokens(tokens));
        return "authenticated";
      }
    },
    [applySession],
  );

  const logout = useCallback(
    (remote = true) => {
      const shouldLogoutFromCognito =
        remote && isCognitoConfigured && session?.provider === "cognito";

      clearPendingPkce();
      clearAuthSession();
      setSession(null);
      setUser(null);
      setError(null);
      setStatus("guest");

      if (shouldLogoutFromCognito) {
        window.location.assign(buildCognitoLogoutUrl());
      }
    },
    [session],
  );

  const refreshProfile = useCallback(async () => {
    if (!session) {
      return null;
    }

    try {
      const profile = await fetchCurrentUser(session.tokens.accessToken);
      setUser(profile);
      return profile;
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        logout(false);
      }
      if (requestError instanceof Error) {
        setError(requestError.message);
      }
      return null;
    }
  }, [logout, session]);

  const value: AuthContextValue = {
    status,
    session,
    user,
    error,
    accessToken: session?.tokens.accessToken ?? null,
    isCognitoConfigured,
    isDevMockAuthEnabled: env.enableDevMockAuth,
    signIn,
    signInDevMock,
    signUpDevMock,
    completeHostedUiLogin,
    logout,
    refreshProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
