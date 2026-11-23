import { describe, expect, it } from "vitest";

import { brainNote } from "./BrainSettings";

describe("Ajustes > Modelo says what the mode does with the Mac as it is", () => {
  it("names the model the Mac offers", () => {
    expect(brainNote({ mode: "local", local_model: "qwen3:4b", mac_online: true })).toMatch(/^O Mac oferece o qwen3:4b\. Responde com o modelo do Mac/);
  });

  it("says when the Mac is on but offers no model", () => {
    expect(brainNote({ mode: "auto", local_model: null, mac_online: true })).toMatch(/sem modelo local configurado/);
  });

  it("reminds that it can be asked in the chat", () => {
    expect(brainNote({ mode: "nuvem", local_model: null, mac_online: false })).toMatch(/usa o modelo local/);
  });
});
