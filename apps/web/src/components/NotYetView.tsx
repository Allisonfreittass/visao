import { Icon, type IconName } from "./Icon";

export interface NotYet {
  icon: IconName;
  title: string;
  /** What the place is for, in his voice. */
  promise: string;
  /** What exists today that comes close, if anything. */
  meanwhile?: string;
}

/** The places the server cannot fill yet (Agentes, Canais, Habilidades): what they are for and
 * an honest "ainda não disponível". No example data: nothing here pretends to work. */
export const NOT_YET: Record<"agents" | "channels" | "skills", NotYet> = {
  agents: {
    icon: "agents",
    title: "Agentes",
    promise: "Aqui vão aparecer as tarefas que eu dividir em partes, cada uma tocada por um agente ao mesmo tempo, com o que cada um já fez.",
    meanwhile: "Hoje eu faço uma coisa por vez. O que roda no Mac aparece em Mac.",
  },
  channels: {
    icon: "plug",
    title: "Canais",
    promise: "Aqui você vai escolher por onde eu posso falar com você: Telegram, WhatsApp, e-mail ou Discord.",
    meanwhile: "Hoje eu aviso por notificação no aparelho, e o e-mail do Google fica em Ajustes › Integrações.",
  },
  skills: {
    icon: "sparkle",
    title: "Habilidades",
    promise: "Aqui vão ficar as habilidades que eu propuser aprender, para você aprovar ou desligar.",
    meanwhile: "Hoje o que eu proponho fazer chega como pedido de aprovação no Início.",
  },
};

export function NotYetView({ place }: { place: keyof typeof NOT_YET }) {
  const info = NOT_YET[place];
  return (
    <section className="page not-yet" aria-labelledby="not-yet-title">
      <header className="page-head">
        <h1 id="not-yet-title">{info.title}</h1>
      </header>
      <div className="not-yet-body">
        <Icon name={info.icon} size={28} />
        <p className="not-yet-flag">Ainda não disponível</p>
        <p className="not-yet-promise">{info.promise}</p>
        {info.meanwhile && <p className="note">{info.meanwhile}</p>}
      </div>
    </section>
  );
}
