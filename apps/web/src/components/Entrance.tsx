import { type FocusEvent, type ReactNode, useState } from "react";

import { CorvoClose } from "../brand/CorvoClose";

/** The fields the crow looks at: the ones you type into, not the checkbox or the buttons. */
function campo(target: EventTarget | null): HTMLInputElement | null {
  return target instanceof HTMLInputElement && target.type !== "checkbox" ? target : null;
}

/** The logged-out entrance: the crow in close on one side, the name, the greeting and the form on
 * the other. `firstAccount`: the form makes the first account instead of signing in. */
export function Entrance({ children, firstAccount = false }: { children: ReactNode; firstAccount?: boolean }) {
  const [alvo, setAlvo] = useState<HTMLInputElement | null>(null);

  function focou(event: FocusEvent) {
    setAlvo(campo(event.target));
  }

  function saiu(event: FocusEvent) {
    // Moving from one field to the next keeps him looking; leaving the fields lets the eye rest.
    if (!campo(event.relatedTarget)) setAlvo(null);
  }

  return (
    <main className="entrada">
      <div className="entrada-corvo">
        <CorvoClose alvo={alvo} />
      </div>
      <section className="entrada-acesso" aria-labelledby="entrada-titulo" onFocus={focou} onBlur={saiu}>
        <p className="entrada-marca" translate="no">VISAO</p>
        <div className="entrada-saudacao">
          <h1 id="entrada-titulo">{firstAccount ? "Bem-vindo." : "Que bom ter você de volta."}</h1>
          <p className="entrada-lede">Só você entra aqui. Ele lembra apenas do que você deixar.</p>
        </div>
        {children}
      </section>
    </main>
  );
}
