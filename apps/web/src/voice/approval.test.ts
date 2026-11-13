import { describe, expect, it } from "vitest";

import { heardVerdict, spokenArm, spokenGoogle } from "./approval";

describe("a spoken yes or no to an action", () => {
  it.each([
    "Pode mandar",
    "pode mandar sim",
    "Sim, pode.",
    "sim",
    "Aprovo.",
    "confirmo",
    "pode rodar",
    "Manda aí",
    "Pode marcar na agenda",
  ])("approves on a clear yes: %s", (said) => expect(heardVerdict(said)).toBe("approve"));

  it.each(["não", "Não, cancela", "cancela isso", "espera", "deixa pra lá", "Recuso"])(
    "rejects on a clear no: %s",
    (said) => expect(heardVerdict(said)).toBe("reject"),
  );

  it.each([
    "não, pode mandar", // mixed
    "sim mas antes muda o assunto para reunião de sexta", // long: a request, not a yes
    "qual é o assunto mesmo?",
    "manda o email pro João também e copia a Maria e depois me lembra amanhã cedo", // long
    "",
    "hmm",
  ])("decides nothing when it is not clear: %s", (said) => expect(heardVerdict(said)).toBeNull());

  it("reads aloud who, what and how to answer", () => {
    const email = spokenGoogle({
      id: "1", kind: "send_email", summary: "Responder João", payload: { to: "joao@exemplo.com", subject: "Reunião" },
      status: "pending", result: "", conversation_id: null, created_at: "",
    });
    expect(email.question).toContain("joao@exemplo.com");
    expect(email.question).toContain('"pode mandar"');
    const mac = spokenArm({
      id: "2", project: "visao", prompt: "rode os testes", status: "proposed", requested_by: "agent",
      result: "", error: "", cost_usd: null, claude_session_id: null, conversation_id: null,
    } as never);
    expect(mac.question).toContain("projeto visao: rode os testes");
  });
});
