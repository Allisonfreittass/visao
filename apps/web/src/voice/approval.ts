// Approving by voice in a call (docs/VOICE.md). It reads aloud exactly what it is about to do
// and waits for a clear yes. Decided by fixed rules, never by a model: a misheard or mixed answer
// decides nothing and goes on as an ordinary message.

import type { ArmTask, GoogleAction } from "../api";

export type Verdict = "approve" | "reject" | null;

/** How long after the question a spoken yes still counts. */
export const VOICE_ANSWER_MS = 3 * 60_000;

const fold = (text: string) =>
  text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const APPROVE = /\b(pode (mandar|enviar|rodar|marcar|agendar|fazer|executar|seguir|criar)|(manda|envia|roda|marca|agenda) (sim|ai|ja|logo)|aprovo|aprovado|confirmo|confirmado|autorizo|autorizado|pode sim|sim pode)\b/;
const REJECT = /\b(nao|cancela|cancelar|cancele|recusa|recuso|recusado|deixa pra la|nem pensar|negativo|espera|espere|pera|para|pare)\b/;
const SHORT_YES = /^(sim|claro|isso|ok|okay|beleza|pode|pode ser|com certeza|manda|envia|bora)( (sim|pode|por favor|obrigado))?$/;

/** What a spoken answer to "posso fazer?" means; null when it is not a clear yes or no. */
export function heardVerdict(text: string): Verdict {
  const said = fold(text);
  if (!said) return null;
  const no = REJECT.test(said);
  const yes = APPROVE.test(said) || (said.split(" ").length <= 4 && SHORT_YES.test(said));
  if (yes && no) return null; // "não, pode mandar": mixed, decide nothing
  if (yes) return "approve";
  if (no && said.split(" ").length <= 6) return "reject";
  return null;
}

export interface SpokenAsk {
  id: string;
  /** Read aloud before asking. */
  question: string;
  /** Said after it was done. */
  done: string;
}

const clip = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1).trimEnd()}…` : text);

export function spokenGoogle(action: GoogleAction): SpokenAsk {
  const p = action.payload;
  if (action.kind === "send_email") {
    return {
      id: action.id,
      question: `Preparei um email para ${p.to ?? "o destinatário"}, assunto: ${clip(p.subject ?? action.summary, 90)}. Para mandar, diga "pode mandar". Para cancelar, diga "não".`,
      done: "Pronto, mandei o email.",
    };
  }
  return {
    id: action.id,
    question: `Preparei um evento na sua agenda: ${clip(p.title ?? action.summary, 90)}. Para marcar, diga "pode marcar". Para cancelar, diga "não".`,
    done: "Pronto, marquei na agenda.",
  };
}

export function spokenArm(task: ArmTask): SpokenAsk {
  return {
    id: task.id,
    question: `Montei um pedido para o Mac, no projeto ${task.project}: ${clip(task.prompt, 140)}. Para rodar, diga "pode rodar". Para cancelar, diga "não".`,
    done: "Pronto, mandei para o Mac. Aviso quando terminar.",
  };
}
