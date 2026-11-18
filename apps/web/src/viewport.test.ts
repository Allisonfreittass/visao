import { describe, expect, it, vi } from "vitest";

import { healShrunkViewport, trackVisibleViewport } from "./viewport";

function fakeWindow(innerHeight: number, vvHeight: number, offsetTop = 0) {
  const listeners: Record<string, () => void> = {};
  const vv = { height: vvHeight, width: 390, offsetTop, addEventListener: (k: string, f: () => void) => (listeners[k] = f), removeEventListener: vi.fn() };
  const scrollTo = vi.fn();
  vi.stubGlobal("window", { visualViewport: vv, innerHeight, scrollY: offsetTop, scrollTo });
  const attrs = new Set<string>();
  const style: Record<string, string> = {};
  const root = {
    clientHeight: innerHeight,
    style: { setProperty: (k: string, v: string) => (style[k] = v), removeProperty: (k: string) => delete style[k] },
    toggleAttribute: (k: string, on: boolean) => (on ? attrs.add(k) : attrs.delete(k)),
  } as unknown as HTMLElement;
  return { vv, listeners, scrollTo, attrs, style, root };
}

describe("the app follows the visible height (the iPhone keyboard)", () => {
  it("leaves the height to the CSS (the whole screen) with the keyboard closed", () => {
    const w = fakeWindow(844, 844);
    trackVisibleViewport(w.root);
    expect(w.style["--app-height"]).toBeUndefined();
    expect(w.attrs.has("data-teclado")).toBe(false);
  });

  it("shrinks to sit on the keyboard and undoes the page scroll iOS makes", () => {
    const w = fakeWindow(844, 844);
    trackVisibleViewport(w.root);
    w.vv.height = 508;
    w.vv.offsetTop = 260;
    w.listeners.resize();
    expect(w.style["--app-height"]).toBe("508px");
    expect(w.attrs.has("data-teclado")).toBe(true);
    expect(w.scrollTo).toHaveBeenCalledWith(0, 0);
    vi.unstubAllGlobals();
  });

  it("knows the keyboard is open even when innerHeight shrinks with it (iPhone)", () => {
    const w = fakeWindow(844, 844);
    trackVisibleViewport(w.root);
    // iOS: both the visible area and innerHeight shrink; only the tallest seen remembers.
    w.vv.height = 470;
    (window as unknown as { innerHeight: number }).innerHeight = 470;
    (w.root as unknown as { clientHeight: number }).clientHeight = 470;
    w.listeners.resize();
    expect(w.attrs.has("data-teclado")).toBe(true);
    expect(w.style["--app-height"]).toBe("470px");
    w.vv.height = 844;
    w.listeners.resize();
    expect(w.attrs.has("data-teclado")).toBe(false);
    expect(w.style["--app-height"]).toBeUndefined();
    vi.unstubAllGlobals();
  });
});

describe("the iPhone app gets its full height back after the keyboard", () => {
  it("hides and shows the app once when the page stayed shorter, keeping the scroll", () => {
    vi.stubGlobal("window", { innerHeight: 785 });
    const list = { scrollTop: 320 };
    const el = { style: { display: "" }, offsetHeight: 0, querySelectorAll: () => [list] } as unknown as HTMLElement;
    expect(healShrunkViewport(844, el)).toBe(true);
    expect(el.style.display).toBe("");
    expect(list.scrollTop).toBe(320);
    vi.unstubAllGlobals();
  });

  it("leaves the app alone when the page has its full height", () => {
    vi.stubGlobal("window", { innerHeight: 844 });
    const el = { style: { display: "" }, querySelectorAll: vi.fn() } as unknown as HTMLElement;
    expect(healShrunkViewport(844, el)).toBe(false);
    vi.unstubAllGlobals();
  });
});
