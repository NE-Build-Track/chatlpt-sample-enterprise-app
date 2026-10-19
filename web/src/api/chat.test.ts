import { describe, expect, it, vi } from "vitest";
import { parseFrame } from "./chat";

describe("parseFrame", () => {
  it("parses a known event", () => {
    const event = parseFrame('event: content\ndata: {"type":"content","text":"hi"}');
    expect(event).toMatchObject({ type: "content", text: "hi" });
  });
  it("ignores comments, bad JSON and events from a newer server", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(parseFrame(": keep-alive")).toBeNull();
    expect(parseFrame("data: not json")).toBeNull();
    expect(parseFrame('data: {"type":"hologram","text":"x"}')).toBeNull();
    expect(warn).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });
});
