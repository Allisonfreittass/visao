import { describe, expect, it } from "vitest";

import { deliveryLine } from "./components/PushToggle";
import { keyBytes, sameKey } from "./push";

const KEY = "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U";
const OTHER = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM";

function subscription(key: Uint8Array | null): PushSubscription {
  return { options: { applicationServerKey: key?.buffer ?? null } } as unknown as PushSubscription;
}

describe("sameKey", () => {
  it("keeps a subscription made for the server's current key", () => {
    expect(sameKey(subscription(keyBytes(KEY)), KEY)).toBe(true);
  });

  it("replaces one made for other VAPID keys, which the push service would refuse", () => {
    expect(sameKey(subscription(keyBytes(OTHER)), KEY)).toBe(false);
  });

  it("trusts browsers that do not expose the key", () => {
    expect(sameKey(subscription(null), KEY)).toBe(true);
  });
});

describe("deliveryLine", () => {
  const base = { at: "2026-11-13T12:00:00Z", devices: 1, sent: 0, errors: [] as string[] };

  it("says when no device was subscribed", () => {
    expect(deliveryLine({ ...base, devices: 0, outcome: "no_device" })).toContain("nenhum aparelho");
  });

  it("explains a refused subscription", () => {
    expect(deliveryLine({ ...base, outcome: "failed", errors: ["http_403"] })).toContain("VAPID");
  });

  it("counts what was delivered", () => {
    expect(deliveryLine({ ...base, outcome: "success", sent: 1 })).toContain("1 de 1");
  });
});
