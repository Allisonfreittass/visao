import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { type Api, ApiError } from "../api";

/** A login that takes longer than this is given up, so the button never hangs on "Verificando…". */
export const LOGIN_TIMEOUT_MS = 20_000;

export interface LoginError {
  text: string;
  /** True when the e-mail or password is what is wrong; false when the server is. */
  credentials: boolean;
}

/** What went wrong, said in the app's voice, and whether to point at the fields. */
export function loginError(e: unknown): LoginError {
  if (e instanceof ApiError) {
    if (e.status === 401) return { text: "E-mail ou senha não conferem.", credentials: true };
    if (e.status === 400 || e.status === 422) return { text: "Confira o e-mail e a senha.", credentials: true };
    // 429 carries the server's own text ("Muitas tentativas. Aguarde alguns minutos.").
    if (e.status === 429) return { text: e.message || "Muitas tentativas. Aguarde alguns minutos.", credentials: false };
    if (e.status >= 500) return { text: "O servidor não respondeu. Seus dados não foram recusados; tente de novo em instantes.", credentials: false };
    return { text: "Não consegui entrar agora. Tente de novo.", credentials: false };
  }
  if (e instanceof DOMException && (e.name === "AbortError" || e.name === "TimeoutError")) {
    return { text: "O servidor demorou para responder. Tente de novo.", credentials: false };
  }
  return { text: "Sem conexão com o servidor. Confira a internet e tente de novo.", credentials: false };
}

interface LoginProps {
  api: Api;
  onLoggedIn: (token: string, remember: boolean) => void;
  /** Last health check: false means the server did not answer it. */
  online?: boolean;
  /** The password field got or lost the focus (the Ciclope closes its eye: "not looking"). */
  onPasswordFocus?: (focused: boolean) => void;
}

export function Login({ api, onLoggedIn, online = true, onPasswordFocus }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(() => window.matchMedia?.("(display-mode: standalone)").matches ?? false);
  const [error, setError] = useState<LoginError | null>(null);
  const [busy, setBusy] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const pending = useRef<AbortController | null>(null);

  // Leaving the screen mid-request cancels it instead of logging in behind the user's back.
  useEffect(() => () => pending.current?.abort(), []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const controller = new AbortController();
    pending.current = controller;
    const timer = window.setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), LOGIN_TIMEOUT_MS);
    setBusy(true);
    setError(null);
    try {
      const token = await api.login(email.trim(), password, controller.signal);
      if (!controller.signal.aborted) onLoggedIn(token, remember);
    } catch (e) {
      const reason: unknown = controller.signal.aborted ? controller.signal.reason : e;
      // An abort that is not the timeout means the screen went away: nothing left to tell.
      if (!controller.signal.aborted || (reason instanceof DOMException && reason.name === "TimeoutError")) {
        setError(loginError(reason));
      }
    } finally {
      window.clearTimeout(timer);
      if (pending.current === controller) pending.current = null;
      setBusy(false);
    }
  }

  function edit(setter: (value: string) => void, value: string) {
    setter(value);
    // The message was about what was typed before; once it changes, it no longer applies.
    if (error?.credentials) setError(null);
  }

  function watchCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState?.("CapsLock") ?? false);
  }

  const fieldError = error?.credentials ? "erro" : undefined;
  const describedBy = error ? "login-error" : undefined;

  return (
    <form className="login" onSubmit={submit} aria-busy={busy}>
      {!online && !error && (
        <p className="login-aviso" role="status">
          O servidor não respondeu à última verificação. Você pode tentar mesmo assim.
        </p>
      )}
      <div className="rs-campo" data-estado={fieldError}>
        <label htmlFor="login-email">E-mail</label>
        <input
          id="login-email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={254}
          value={email}
          onChange={(e) => edit(setEmail, e.target.value)}
          aria-invalid={error?.credentials || undefined}
          aria-describedby={describedBy}
          required
        />
      </div>
      <div className="rs-campo" data-estado={fieldError}>
        <label htmlFor="login-password">Senha</label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          maxLength={1024}
          value={password}
          onChange={(e) => edit(setPassword, e.target.value)}
          onKeyDown={watchCapsLock}
          onKeyUp={watchCapsLock}
          onFocus={() => onPasswordFocus?.(true)}
          onBlur={() => {
            setCapsLock(false);
            onPasswordFocus?.(false);
          }}
          aria-invalid={error?.credentials || undefined}
          aria-describedby={[describedBy, capsLock ? "login-caps" : undefined].filter(Boolean).join(" ") || undefined}
          required
        />
        {capsLock && <small id="login-caps">Caps Lock está ligado.</small>}
      </div>
      <label className="memory-toggle">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        Manter conectado neste aparelho
      </label>
      {error && (
        <p id="login-error" className="login-erro" role="alert">
          {error.text}
        </p>
      )}
      <button type="submit" className="rs-botao rs-botao--principal" disabled={busy}>
        {busy ? "Verificando…" : "Acessar"}
      </button>
    </form>
  );
}
