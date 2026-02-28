import { describe, expect, it } from "vitest";
import { isTerminalStudyStatus } from "@/hooks/useStudyStatusPolling";

describe("isTerminalStudyStatus", () => {
  it("returns true for COMPLETED and FAILED", () => {
    expect(isTerminalStudyStatus("COMPLETED")).toBe(true);
    expect(isTerminalStudyStatus("FAILED")).toBe(true);
  });

  it("returns false for active states", () => {
    expect(isTerminalStudyStatus("PROCESSING")).toBe(false);
    expect(isTerminalStudyStatus("SUBMITTED")).toBe(false);
  });
});
