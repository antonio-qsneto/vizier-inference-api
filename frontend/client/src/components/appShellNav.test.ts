import { describe, expect, it } from "vitest";
import { getActiveNavHref } from "@/components/appShellNav";

const navItems = [
  { href: "/dashboard" },
  { href: "/studies" },
  { href: "/studies/new" },
  { href: "/clinic" },
  { href: "/billing" },
];

describe("getActiveNavHref", () => {
  it("marks /studies/new as the exam upload entry only", () => {
    expect(getActiveNavHref("/studies/new", navItems)).toBe("/studies/new");
  });

  it("marks /studies/:id under clinical cases", () => {
    expect(getActiveNavHref("/studies/123", navItems)).toBe("/studies");
  });

  it("marks /studies/:id/viewer under clinical cases", () => {
    expect(getActiveNavHref("/studies/123/viewer", navItems)).toBe("/studies");
  });

  it("matches direct paths like /billing", () => {
    expect(getActiveNavHref("/billing", navItems)).toBe("/billing");
  });

  it("returns null for unknown routes", () => {
    expect(getActiveNavHref("/unknown", navItems)).toBeNull();
  });
});
