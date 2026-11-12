import { useEffect, useState } from "react";

import type { Api, PushState } from "../api";
import { currentSubscription, pushSupport, subscribe, unsubscribe } from "../push";

interface PushToggleProps {
  api: Api;
  onError: (e: unknown) => void;
}

/** Opt-in, per device: lets an opening reach this phone or computer with the app closed. */
export function PushToggle({ api, onError }: PushToggleProps) {
  const [server, setServer] = useState<PushState | null>(null);
  const [on, setOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const support = pushSupport();

  useEffect(() => {
    api.pushState().then(setServer).catch(() => setServer(null));
    if (support === "supported") currentSubscription().then((s) => setOn(s !== null)).catch(() => undefined);
  }, [api, support]);

  async function toggle() {
    if (!server?.public_key) return;
    setBusy(true);
    setNote(null);
    try {
      if (on) {
        await unsubscribe(api);
        setOn(false);
      } else {
        await subscribe(api, server.public_key);
        setOn(true);
        setNote("Pronto. Quando eu tiver algo a dizer, chego aqui.");
      }
    } catch (e) {
      setNote(e instanceof Error ? `Não deu: ${e.message}.` : "Não deu certo.");
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    try {
      const { sent } = await api.testPush();
      setNote(sent > 0 ? "Mandei um teste. Feche o app para ver chegar." : "Nenhum aparelho recebeu.");
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  }

  const reason = !server
    ? "Não consegui saber se os avisos estão ligados no servidor."
    : !server.enabled
      ? "Os avisos ainda não foram configurados no servidor (chaves VAPID)."
      : support === "needs-install"
        ? "No iPhone, os avisos só funcionam com o app na tela de início: Compartilhar → Adicionar à Tela de Início."
        : support === "unsupported"
          ? "Este navegador não recebe avisos."
          : null;

  return (
    <div className="preference">
      <label className="memory-toggle">
        <input type="checkbox" checked={on} onChange={toggle} disabled={busy || reason !== null} />
        Avisos com o app fechado
      </label>
      <p className="note">{reason ?? note ?? "Quando eu puxar conversa, aviso neste aparelho. Respeito o seu horário de silêncio."}</p>
      {on && !reason && <button type="button" className="link-button" onClick={test} disabled={busy}>Mandar um teste</button>}
    </div>
  );
}
