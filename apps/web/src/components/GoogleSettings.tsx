import { type FormEvent, useEffect, useRef, useState } from "react";

import type { Api, GoogleState } from "../api";
import { Setting } from "./Setting";
import { confirmar } from "../ask";

const SIGN_IN_WAIT_MS = 10 * 60 * 1000;

type Signing = { step: "abrindo" } | { step: "esperando"; url?: string } | { step: "erro"; message: string };

/** Where Google comes back to, on this address: registered once in the "Web application" client. */
export function callbackAddress(origin: string): string {
  return `${origin}/api/google/web/callback`;
}

const PERMISSION: Record<string, string> = {
  "gmail.readonly": "ler o Gmail",
  "gmail.send": "mandar email",
  "calendar.events": "a agenda",
};

const WHY: Record<string, string> = {
  vencido: "Esse login venceu (10 minutos) ou já foi usado. Toque em Conectar de novo.",
  navegador: "O login terminou num navegador diferente do que começou. Comece e termine no mesmo aparelho e no mesmo navegador.",
  recusado: "O Google não autorizou: o login foi cancelado ou negado.",
  troca: "O Google recusou a troca do código. Confira a chave secreta do cliente (uma chave nova pode levar alguns minutos para valer) e se o endereço de retorno está cadastrado.",
  google: "O Google aceitou o login, mas a primeira leitura falhou. Confira se a Gmail API e a Google Calendar API estão ativas no projeto.",
};

/**
 * What the server said when Google sent the browser back (`/?google=conectado` or
 * `/?google=erro&motivo=…`, apps/api/routes/google.py), in words; null without it.
 */
export function googleReturn(search: string): { ok: boolean; text: string } | null {
  const params = new URLSearchParams(search);
  const result = params.get("google");
  if (result === "conectado") {
    const missing = (params.get("faltou") ?? "").split(",").filter(Boolean).map((s) => PERMISSION[s] ?? s);
    const text = "Google conectado. Agora eu leio seu email e sua agenda quando você pedir.";
    return { ok: true, text: missing.length ? `${text} Você não marcou ${missing.join(" e ")}; essa parte não vai funcionar.` : text };
  }
  if (result === "erro") return { ok: false, text: WHY[params.get("motivo") ?? ""] ?? "Não deu para conectar o Google. Tente de novo." };
  return null;
}

/** Takes the Google return out of the address, so a reload does not say it again. */
function clearReturn() {
  const url = new URL(window.location.href);
  for (const key of ["google", "motivo", "faltou"]) url.searchParams.delete(key);
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
}

/**
 * The hosted server's "Conectar": the ID and the secret of the owner's own "Web application"
 * client, typed once. The page then goes to Google in this same tab and comes back here; the
 * secret is kept encrypted with the connection on the server and never shown again.
 */
function WebConnect({ api, again }: { api: Api; again: boolean }) {
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const callback = callbackAddress(window.location.origin);

  async function go(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { url } = await api.googleWebStart(clientId.trim(), secret.trim());
      setSecret("");
      window.location.assign(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <form className="google-web" onSubmit={(e) => void go(e)}>
      <p className="note">
        {again ? "Informe de novo" : "Na primeira vez, informe"} o ID e a chave secreta do seu cliente do Google, do tipo
        "Aplicativo da Web", com este endereço de retorno cadastrado (o passo a passo está no docs/GOOGLE.md):
      </p>
      <code>{callback}</code>
      <label className="setting-title" htmlFor="google-client-id">ID do cliente</label>
      <input
        id="google-client-id"
        className="settings-search"
        autoComplete="off"
        spellCheck={false}
        placeholder="…apps.googleusercontent.com"
        value={clientId}
        onChange={(e) => setClientId(e.target.value)}
        required
      />
      <label className="setting-title" htmlFor="google-client-secret">Chave secreta do cliente</label>
      <input
        id="google-client-secret"
        className="settings-search"
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={secret}
        onChange={(e) => setSecret(e.target.value)}
        required
      />
      <p className="note">A chave fica guardada cifrada no servidor, junto da conexão, e não volta para a tela.</p>
      {error && <p className="error">{error}</p>}
      <button type="submit" disabled={busy || !clientId.trim() || !secret.trim()}>
        {busy ? "Abrindo o Google…" : again ? "Conectar de novo" : "Conectar"}
      </button>
    </form>
  );
}

/** Gmail and Google Calendar: whether they are connected, and the one switch that matters. */
export function GoogleSettings({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [state, setState] = useState<GoogleState | null>(null);
  const [signing, setSigning] = useState<Signing | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [returned] = useState(() => googleReturn(window.location.search));

  useEffect(() => {
    if (returned) clearReturn();
  }, [returned]);

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
    if (!(await confirmar("Desconectar o Google? Eu paro de ler seu email e sua agenda na hora.", "Desconectar"))) return;
    try {
      await api.googleDisconnect();
      setState(await api.google());
    } catch (e) {
      onError(e);
    }
  }

  async function start(client?: unknown) {
    setSigning({ step: "abrindo" });
    try {
      const { url, opened } = await api.googleStart(client);
      setSigning({ step: "esperando", url: opened ? undefined : url });
    } catch (e) {
      setSigning({ step: "erro", message: e instanceof Error ? e.message : String(e) });
    }
  }

  async function pickedFile(file: File | undefined) {
    if (!file) return;
    try {
      await start(JSON.parse(await file.text()));
    } catch {
      setSigning({ step: "erro", message: "Esse arquivo não é o JSON do cliente do Google." });
    }
  }

  // While the sign-in happens in the browser, the server is asked every few seconds.
  useEffect(() => {
    if (signing?.step !== "esperando") return;
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (Date.now() - started > SIGN_IN_WAIT_MS) {
        setSigning({ step: "erro", message: "Passaram 10 minutos sem o login. Tente de novo." });
        return;
      }
      api.google().then((next) => {
        if (next.connected) {
          setState(next);
          setSigning(null);
        }
      }, () => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [api, signing?.step]);

  if (!state) return null;
  if (!state.connected) {
    return (
      <div className="setting">
        <div className="setting-text">
          <span className="setting-title">Gmail e Google Agenda</span>
          <p className="note">
            Desconectado. Conecte para eu ler seu email e sua agenda quando você pedir (e preparar
            respostas e eventos para você aprovar).
          </p>
          {state.connect_here ? (
            <>
              {signing?.step === "esperando" && (
                <p className="note">
                  Abri o login do Google no navegador. Termine lá e volte aqui: eu percebo sozinho.
                  {signing.url && <> Se não abriu, <a href={signing.url} target="_blank" rel="noopener noreferrer">abra este endereço</a>.</>}
                </p>
              )}
              {signing?.step === "erro" && <p className="error">{signing.message}</p>}
              {!state.client_ready && signing?.step !== "esperando" && (
                <p className="note">
                  Na primeira vez, escolha o arquivo do cliente do Google (o JSON de um "App para
                  computador" criado no Google Cloud, como explica o docs/GOOGLE.md).
                </p>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                hidden
                onChange={(e) => { void pickedFile(e.target.files?.[0]); e.target.value = ""; }}
              />
            </>
          ) : (
            <>
              {returned && <p className={returned.ok ? "note" : "error"}>{returned.text}</p>}
              <WebConnect api={api} again={false} />
              <details className="google-terminal">
                <summary className="note">Ou pelo terminal do seu computador</summary>
                <code>python -m apps.api.cli google-connect --client-file cliente.json --server {window.location.origin}</code>
              </details>
            </>
          )}
        </div>
        {state.connect_here && (
          <button
            type="button"
            disabled={signing?.step === "abrindo"}
            onClick={() => (state.client_ready ? void start() : fileRef.current?.click())}
          >
            {signing?.step === "esperando" ? "Abrir de novo" : state.client_ready ? "Conectar com o Google" : "Escolher arquivo e conectar"}
          </button>
        )}
      </div>
    );
  }
  return (
    <>
      <div className="setting">
        <div className="setting-text">
          <span className="setting-title">Gmail e Google Agenda</span>
          <p className="note">Conectado como {state.email}. Leio quando você pergunta; mandar ou marcar algo só com o seu sim.</p>
          {returned && <p className={returned.ok ? "note" : "error"}>{returned.text}</p>}
          {state.problem && <p className="error">{state.problem}</p>}
          {state.reconnect && <WebConnect api={api} again />}
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
