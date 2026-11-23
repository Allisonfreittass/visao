import { type ReactNode, useEffect, useState } from "react";

import { Genesis } from "./Genesis";
import "./muninn.css";

function clock(date: Date): string {
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** The logged-out entrance in Muninn (DESIGN.md §8 step 4): the ring and the raven on one side,
 * his greeting and the form on the other. Muninn's tokens and fonts live only inside it for now. */
export function MuninnEntrance({ thinking, children }: { thinking: boolean; children: ReactNode }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <main className="muninn-entrada">
      <header className="muninn-barra">
        <span className="muninn-codinome">Visão</span>
        <time className="muninn-hora" dateTime={now.toISOString()}>
          {clock(now)}
        </time>
      </header>
      <div className="muninn-palco">
        <div className="muninn-marca">
          <Genesis thinking={thinking} />
        </div>
        <section className="muninn-acesso" aria-labelledby="muninn-saudacao">
          <h1 id="muninn-saudacao">Bem-vindo de volta.</h1>
          {children}
        </section>
      </div>
    </main>
  );
}
