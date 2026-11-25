import { describe, expect, it } from "vitest";

import { NOT_YET } from "./NotYetView";

describe("Canais while it does not exist", () => {
  it("points to where the apps connected through Composio live", () => {
    const meanwhile = NOT_YET.channels.meanwhile ?? "";
    expect(meanwhile).toContain("Ajustes › Integrações › Apps");
    expect(meanwhile).toContain("ainda não converso com você por lá");
  });
});
