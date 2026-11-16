import { describe, expect, it } from "vitest";
import { asksNearby, positionFor } from "./location";

describe("asksNearby", () => {
  it("matches questions about somewhere near, not the word perto in passing", () => {
    for (const t of ["tem farmácia aberta aqui perto?", "qual o posto mais perto?", "algum restaurante bom por aqui?", "onde tem caixa eletrônico perto de mim", "tem padaria perto?"]) {
      expect(asksNearby(t)).toBe(true);
    }
    for (const t of ["estou perto de terminar o projeto", "já está perto do Natal", "daqui a pouco te respondo", "aqui está o link que te falei"]) {
      expect(asksNearby(t)).toBe(false);
    }
  });
});

describe("positionFor", () => {
  it("sends nothing while the switch is off", async () => {
    expect(await positionFor("tem farmácia aqui perto?")).toBeNull();
  });
});
