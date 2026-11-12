import { type FormEvent, useEffect, useState } from "react";

import { type Api, ApiError } from "../api";
import { saveToken, tokenRemembered } from "../session";

interface AccountPanelProps {
  api: Api;
}

type Mode = "password" | "email" | null;

/** Email and password, changed with the current password; every other session is signed out. */
export function AccountPanel({ api }: AccountPanelProps) {
  const [email, setEmail] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.me().then((me) => setEmail(me.email)).catch(() => setEmail(null));
  }, [api]);

  function open(which: Mode) {
    setMode(which);
    setCurrent("");
    setNext("");
    setConfirm("");
    setMessage(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "password" && next !== confirm) {
      setMessage({ ok: false, text: "As senhas novas não conferem." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const token = mode === "password"
        ? await api.changePassword(current, next)
        : await api.changeEmail(current, next);
      saveToken(token, tokenRemembered());
      if (mode === "email") setEmail(next.trim().toLowerCase());
      setMode(null);
      setMessage({
        ok: true,
        text: mode === "password"
          ? "Senha trocada. Os outros aparelhos vão pedir login de novo."
          : "Email trocado. Os outros aparelhos vão pedir login de novo.",
      });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : "Não consegui trocar agora." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="setting setting--conta">
      <div className="setting-text">
      <span className="setting-title">Login</span>
      <p className="note">{email ?? "…"}</p>
      {mode === null && (
        <div className="account-actions">
          <button type="button" className="link-button" onClick={() => open("password")}>Trocar senha</button>
          <button type="button" className="link-button" onClick={() => open("email")}>Trocar email</button>
        </div>
      )}
      {mode !== null && (
        <form className="account-form" onSubmit={submit}>
          <div className="rs-campo">
            <label htmlFor="account-current">Senha atual</label>
            <input id="account-current" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
          </div>
          <div className="rs-campo">
            <label htmlFor="account-next">{mode === "password" ? "Senha nova" : "Email novo"}</label>
            <input
              id="account-next"
              type={mode === "password" ? "password" : "email"}
              autoComplete={mode === "password" ? "new-password" : "email"}
              minLength={mode === "password" ? 12 : undefined}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
            {mode === "password" && <small>Pelo menos 12 caracteres.</small>}
          </div>
          {mode === "password" && (
            <div className="rs-campo">
              <label htmlFor="account-confirm">Confirme a senha nova</label>
              <input id="account-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
            </div>
          )}
          <div className="account-actions">
            <button type="submit" className="rs-botao" disabled={busy}>{busy ? "Trocando…" : "Trocar"}</button>
            <button type="button" className="link-button" onClick={() => open(null)}>Cancelar</button>
          </div>
        </form>
      )}
      {message && <p className={message.ok ? "note" : "error"} role="status">{message.ok ? "✓ " : "× "}{message.text}</p>}
      </div>
    </div>
  );
}
