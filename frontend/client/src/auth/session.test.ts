import { describe, expect, it } from "vitest";
import {
  createDevelopmentSession,
  createSessionFromTokens,
  isSessionUsable,
} from "@/auth/session";

describe("auth session helpers", () => {
  it("creates a usable development session", () => {
    const session = createDevelopmentSession();
    expect(session.tokens.accessToken).toBe("dev-token");
    expect(isSessionUsable(session)).toBe(true);
  });

  it("converts token exchange payload to absolute expiration", () => {
    const before = Date.now();
    const session = createSessionFromTokens({
      access_token: "abc",
      expires_in: 60,
    });

    expect(session.tokens.accessToken).toBe("abc");
    expect(session.tokens.expiresAt).toBeGreaterThan(before);
  });
});
