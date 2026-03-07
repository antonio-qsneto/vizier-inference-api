import { describe, expect, it } from "vitest";
import {
  consumeAuthNotice,
  createDevelopmentSession,
  createSessionFromTokens,
  isSessionUsable,
  saveAuthNotice,
} from "@/auth/session";

describe("auth session helpers", () => {
  it("creates a usable development session", () => {
    const session = createDevelopmentSession();
    expect(session.provider).toBe("local_fallback");
    expect(session.tokens.accessToken).toBe("dev-token");
    expect(isSessionUsable(session)).toBe(true);
  });

  it("converts token exchange payload to absolute expiration", () => {
    const before = Date.now();
    const session = createSessionFromTokens({
      access_token: "abc",
      expires_in: 60,
    });

    expect(session.provider).toBe("cognito");
    expect(session.tokens.accessToken).toBe("abc");
    expect(session.tokens.expiresAt).toBeGreaterThan(before);
  });

  it("persists and consumes auth notices once", () => {
    saveAuthNotice("Cadastro concluido. Faca login para continuar.");

    expect(consumeAuthNotice()).toBe(
      "Cadastro concluido. Faca login para continuar.",
    );
    expect(consumeAuthNotice()).toBeNull();
  });
});
