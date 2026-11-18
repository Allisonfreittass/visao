import { type FormEvent, useState } from "react";

import { type Api, ApiError } from "../api";

interface LoginProps {
  api: Api;
  onLoggedIn: (token: string, remember: boolean) => void;
  /** The password field got or lost the focus (the Ciclope closes its eye: "not looking"). */
  onPasswordFocus?: (focused: boolean) => void;
}

export function Login({ api, onLoggedIn, onPasswordFocus }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(() => window.matchMedia?.("(display-mode: standalone)").matches ?? false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLoggedIn(await api.login(email.trim(), password), remember);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não consegui falar com o servidor.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="login" onSubmit={submit}>
      <div className="rs-campo">
        <label htmlFor="login-email">Email</label>
        <input id="login-email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </div>
      <div className="rs-campo" data-estado={error ? "erro" : undefined}>
        <label htmlFor="login-password">Senha</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onFocus={() => onPasswordFocus?.(true)}
          onBlur={() => onPasswordFocus?.(false)}
          required
          aria-describedby={error ? "login-error" : undefined}
        />
        {error && <small id="login-error" role="alert">× {error}</small>}
      </div>
      <label className="memory-toggle">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        Manter conectado
      </label>
      <button type="submit" className="rs-botao rs-botao--principal" disabled={busy}>
        {busy ? "Entrando…" : "Entrar"}
      </button>
    </form>
  );
}
