import { useEffect, useMemo, useRef, useState } from "react";

import { Anel } from "../anel/Anel";
import type { AnelEstado } from "../anel/state";
import { Nanorrobos } from "./Nanorrobos";
import { DESENHOS, FADE_MS, type Ferramenta, type Forma, MORPH_MS, type Passo, agendaInicial, formaDoPasso, pathOf, pedir, proximaTroca } from "./nanorrobos";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

/** The shape the turn's steps ask for, each one held at least HOLD_MS once formed. */
function useForma(passo: Passo | null, morphMs: number): Forma {
  const [agenda, setAgenda] = useState(agendaInicial);
  const desejada = useRef<Forma>("corvo");

  useEffect(() => {
    desejada.current = formaDoPasso(passo, desejada.current);
    const wanted = desejada.current;
    setAgenda((a) => pedir(a, wanted, performance.now(), morphMs));
  }, [passo, morphMs]);

  // The shape waiting for its turn shows as soon as the current one has had its time.
  useEffect(() => {
    const at = proximaTroca(agenda);
    if (at === null) return;
    const id = window.setTimeout(
      () => setAgenda((a) => (a.pendente === null ? a : pedir(a, a.pendente, performance.now(), morphMs))),
      Math.max(0, at - performance.now()) + 5,
    );
    return () => window.clearTimeout(id);
  }, [agenda, morphMs]);

  return agenda.forma;
}

interface MuninnDaLigacaoProps {
  estado: AnelEstado;
  size: number;
  level: () => number;
  /** The turn's latest step (null between turns). */
  passo: Passo | null;
}

/** Muninn in the call (DESIGN.md §6, "Nanorrobôs"): his particles take the shape of the tool he
 * uses and come back to the crow; the ring round him keeps its states. With reduced motion the
 * crow and a line icon of the tool cross-fade instead. */
export function MuninnDaLigacao({ estado, size, level, passo }: MuninnDaLigacaoProps) {
  const quieto = useMemo(reducedMotion, []);
  const forma = useForma(passo, quieto ? FADE_MS : MORPH_MS);
  const ferramenta = forma === "corvo" ? null : forma;
  // The icon fading out is still the last tool's.
  const ultima = useRef<Ferramenta | null>(null);
  if (ferramenta) ultima.current = ferramenta;

  if (quieto) {
    return (
      <div className={`nano${ferramenta ? " nano--ferramenta" : ""}`} data-forma={forma} style={{ width: size, height: size }}>
        <Anel estado={estado} size={size} level={level} decorative />
        <svg className="nano-icone" viewBox="0 0 1000 1000" aria-hidden="true" focusable="false">
          {ultima.current && <path d={pathOf(DESENHOS[ultima.current])} vectorEffect="non-scaling-stroke" />}
        </svg>
      </div>
    );
  }
  return (
    <div className="nano" data-forma={forma} style={{ width: size, height: size }}>
      <Nanorrobos forma={forma} />
      <Anel estado={estado} size={size} level={level} decorative vazio />
    </div>
  );
}
