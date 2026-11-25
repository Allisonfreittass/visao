import type { ReactNode } from "react";

import { Selo } from "../brand/Selo";

/** The logged-out entrance: the seal on one side, the greeting and the form on the other.
 * `firstAccount`: on the owner's machine with nobody signed up, the form makes the account. */
export function Entrance({ children, firstAccount = false }: { children: ReactNode; firstAccount?: boolean }) {
  return (
    <main className="entrada">
      <Selo className="entrada-selo" />
      <section className="entrada-acesso" aria-labelledby="entrada-titulo">
        <h1 id="entrada-titulo">{firstAccount ? "Bem-vindo." : "Bem-vindo de volta."}</h1>
        <p className="entrada-lede">Só você entra aqui. Ele lembra apenas do que você deixar.</p>
        {children}
        {firstAccount ? (
          <p className="entrada-nota">Depois de criar a conta, ele te guia em quatro passos.</p>
        ) : (
          <p className="entrada-nota">Primeira vez? A conta é criada no servidor, com <code>python -m apps.api.cli create-user</code>. Depois de entrar, ele te guia em quatro passos.</p>
        )}
      </section>
    </main>
  );
}
