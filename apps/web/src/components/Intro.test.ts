import { describe, expect, it } from "vitest";

import { greeting, shouldPlayIntro } from "./Intro";

describe("greeting", () => {
  it("follows the hour on this device", () => {
    expect(greeting(6)).toBe("Bom dia");
    expect(greeting(13)).toBe("Boa tarde");
    expect(greeting(20)).toBe("Boa noite");
    expect(greeting(2)).toBe("Boa noite");
  });
});

describe("shouldPlayIntro", () => {
  const now = new Date(2026, 10, 17, 9, 0);
  it("plays once a day", () => {
    expect(shouldPlayIntro(now, null, false)).toBe(true);
    expect(shouldPlayIntro(now, "2026-11-16", false)).toBe(true);
    expect(shouldPlayIntro(now, "2026-11-17", false)).toBe(false);
  });
  it("never plays for someone who asked for less motion", () => {
    expect(shouldPlayIntro(now, null, true)).toBe(false);
  });
});
