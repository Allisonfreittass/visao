import { afterEach, describe, expect, it, vi } from "vitest";

import { useBackClose } from "./useBackClose";

// The hook's effect, run by hand: React would call it on open and its cleanup on close.
vi.mock("react", () => ({
  useRef: (v: unknown) => ({ current: v }),
  useEffect: (fn: () => (() => void) | void) => {
    effects.push(fn);
  },
}));
const effects: (() => (() => void) | void)[] = [];

function fakeHistory() {
  const stack: unknown[] = [{}];
  const listeners = new Set<() => void>();
  const history = {
    get state() {
      return stack[stack.length - 1];
    },
    pushState: (s: unknown) => stack.push(s),
    back: () => {
      stack.pop();
      setTimeout(() => listeners.forEach((l) => l()), 0);
    },
    get length() {
      return stack.length;
    },
  };
  vi.stubGlobal("window", {
    history,
    setTimeout: globalThis.setTimeout,
    clearTimeout: globalThis.clearTimeout,
    addEventListener: (_: string, l: () => void) => listeners.add(l),
    removeEventListener: (_: string, l: () => void) => listeners.delete(l),
  });
  return { history, back: () => history.back() };
}

afterEach(() => {
  effects.length = 0;
  vi.unstubAllGlobals();
});

describe("Back closes what is open", () => {
  it("survives a mount-unmount-mount (strict mode) and Back still closes it", async () => {
    const { history, back } = fakeHistory();
    const onClose = vi.fn();
    useBackClose(true, onClose);
    const first = effects[0]()!;
    first(); // strict mode: cleanup at once
    const second = effects[0]()!;
    await new Promise((r) => setTimeout(r, 5));
    expect(history.length).toBe(2);
    expect(onClose).not.toHaveBeenCalled();
    back();
    await new Promise((r) => setTimeout(r, 5));
    expect(onClose).toHaveBeenCalledTimes(1);
    second();
  });

  it("closing it by its own button takes the entry back out", async () => {
    const { history } = fakeHistory();
    useBackClose(true, vi.fn());
    const cleanup = effects[0]()!;
    await new Promise((r) => setTimeout(r, 5));
    expect(history.length).toBe(2);
    cleanup();
    expect(history.length).toBe(1);
  });
});
