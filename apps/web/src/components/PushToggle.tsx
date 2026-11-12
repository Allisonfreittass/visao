import { useEffect, useState } from "react";

import type { Api, PushState } from "../api";
import { currentSubscription, pushSupport, subscribe, unsubscribe } from "../push";
import { Setting } from "./Setting";

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
        ? "No iPhone, só com o app na tela de início: Compartilhar, depois Adicionar à Tela de Início."
        : support === "unsupported"
          ? "Este navegador não recebe avisos."
          : null;

  return (
    <Setting
      title="Avisos neste aparelho"
      description={reason ?? note ?? "Te chamo mesmo com o app fechado. Respeito o seu horário de silêncio."}
      checked={on}
      disabled={busy || reason !== null}
      onChange={() => void toggle()}
    >
      {on && !reason && <button type="button" className="link-button" onClick={() => void test()} disabled={busy}>Mandar um teste</button>}
    </Setting>
  );
}
