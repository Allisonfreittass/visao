import { useEffect, useState } from "react";

import type { Api, PushDelivery, PushState } from "../api";
import { utcDate } from "../api";
import { currentSubscription, pushSupport, subscribe, syncSubscription, unsubscribe } from "../push";
import { Setting } from "./Setting";

/** Time to lock the phone before the test aviso goes out. */
const TEST_DELAY_SECONDS = 8;

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
    let alive = true;
    // Sync first, so the switch and the device count describe what the server really has.
    syncSubscription(api)
      .catch(() => false)
      .then(() => api.pushState())
      .then((state) => alive && setServer(state))
      .catch(() => alive && setServer(null));
    if (support === "supported") {
      currentSubscription().then((s) => alive && setOn(s !== null)).catch(() => undefined);
    }
    return () => {
      alive = false;
    };
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
      // On iPhone an aviso that arrives with the app open may not show: wait until it is closed.
      const { scheduled } = await api.testPush(TEST_DELAY_SECONDS);
      setNote(
        scheduled > 0
          ? `Bloqueie a tela agora: o teste chega em ${TEST_DELAY_SECONDS} segundos.`
          : "Nenhum aparelho inscrito para receber.",
      );
      window.setTimeout(() => {
        api.pushState().then(setServer).catch(() => undefined);
      }, (TEST_DELAY_SECONDS + 3) * 1000);
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

  const last = server?.last_delivery ? deliveryLine(server.last_delivery) : null;

  return (
    <Setting
      title="Avisos neste aparelho"
      description={reason ?? note ?? "Te chamo mesmo com o app fechado. Respeito o seu horário de silêncio."}
      checked={on}
      disabled={busy || reason !== null}
      onChange={() => void toggle()}
    >
      {last && !reason && <p className="note">{last}</p>}
      {on && !reason && <button type="button" className="link-button" onClick={() => void test()} disabled={busy}>Mandar um teste</button>}
    </Setting>
  );
}

const DELIVERY_ERRORS: Record<string, string> = {
  http_403: "o serviço de push recusou a assinatura (chaves VAPID trocadas ou assunto inválido)",
  http_404: "a inscrição deste aparelho não existe mais",
  http_410: "a inscrição deste aparelho expirou",
  http_413: "a mensagem ficou grande demais",
  http_429: "o serviço de push pediu para esperar",
};

/** One sentence on what happened to the last aviso, for "it never came". */
export function deliveryLine(delivery: PushDelivery): string {
  const when = utcDate(delivery.at).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  switch (delivery.outcome) {
    case "success":
      return `Último aviso (${when}): entregue a ${delivery.sent} de ${delivery.devices} aparelho(s).`;
    case "no_device":
      return `Último aviso (${when}): não saiu, nenhum aparelho estava inscrito no servidor.`;
    case "disabled":
      return `Último aviso (${when}): não saiu, o push estava desligado no processo que mandou.`;
    default: {
      const code = delivery.errors[0] ?? "";
      const why = DELIVERY_ERRORS[code] ?? (code || "erro sem detalhe");
      return `Último aviso (${when}): falhou, ${why}.`;
    }
  }
}
