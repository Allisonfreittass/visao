import { useEffect, useState } from "react";

import type { Api, GoogleState } from "../api";
import { Setting } from "./Setting";

/** Gmail and Google Calendar: whether they are connected, and the one switch that matters. */
export function GoogleSettings({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [state, setState] = useState<GoogleState | null>(null);

  useEffect(() => {
    api.google().then(setState).catch(onError);
  }, [api, onError]);

  async function toggle() {
    if (!state) return;
    try {
      setState(await api.googleBackground(!state.background));
    } catch (e) {
      onError(e);
    }
  }

  async function disconnect() {
    if (!window.confirm("Desconectar o Google? Eu paro de ler seu email e sua agenda na hora.")) return;
    try {
      await api.googleDisconnect();
      setState(await api.google());
    } catch (e) {
      onError(e);
    }
  }

  if (!state) return null;
  if (!state.connected) {
    return (
      <div className="setting">
        <div className="setting-text">
          <span className="setting-title">Gmail e Google Agenda</span>
          <p className="note">
            Desconectado. Para eu ler seu email e sua agenda (e preparar respostas e eventos para você
            aprovar), conecte pelo seu computador:
          </p>
          <code>python -m apps.api.cli google-connect --client-file cliente.json --server {window.location.origin}</code>
        </div>
      </div>
    );
  }
  return (
    <>
      <div className="setting">
        <div className="setting-text">
          <span className="setting-title">Gmail e Google Agenda</span>
          <p className="note">Conectado como {state.email}. Leio quando você pergunta; mandar ou marcar algo só com o seu sim.</p>
          {state.problem && <p className="error">{state.problem}</p>}
        </div>
        <button type="button" className="ghost" onClick={() => void disconnect()}>Desconectar</button>
      </div>
      <Setting
        title="Olhar email e agenda sozinho"
        description="Vejo os compromissos das próximas 24 h e os assuntos dos emails não lidos, nunca o texto, para te lembrar do que importa."
        checked={state.background}
        onChange={() => void toggle()}
      />
    </>
  );
}
