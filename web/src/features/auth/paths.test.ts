import { describe, expect, it } from "vitest";
import { localPath, signInError } from "./paths";

describe("localPath", () => {
  it("keeps paths on this site", () => {
    expect(localPath("/c/123")).toBe("/c/123");
    expect(localPath("/admin?x=1")).toBe("/admin?x=1");
  });
  it("refuses anything that leaves the site", () => {
    for (const bad of ["https://evil", "//evil.com", "/\\evil.com", "/\t/evil.com", "\\evil", "evil", "", null]) {
      expect(localPath(bad)).toBe("/");
    }
  });
});

describe("signInError", () => {
  it("explains each reason and has a fallback", () => {
    expect(signInError("cancelled")).toBe("Sign-in was cancelled.");
    expect(signInError("something-new")).toBe("Sign-in failed. Try again.");
    expect(signInError(null)).toBeNull();
  });
});
