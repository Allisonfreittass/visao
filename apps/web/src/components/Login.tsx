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

/** The first account needs a password at least this long (the server says the same). */
export const MIN_PASSWORD_LENGTH = 12;

/** The field left empty, said before anything goes to the server, or null. */
export interface MissingField {
  field: "email" | "password";
  text: string;
}

export function missingField(email: string, password: string): MissingField | null {
  if (!email.trim()) return { field: "email", text: "Digite o e-mail para entrar." };
  if (!password) return { field: "password", text: "Digite a senha para entrar." };
  return null;
}

/** What is wrong with the first account before it goes to the server, or null. */
export function firstRunProblem(password: string, confirm: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) return `A senha precisa de pelo menos ${MIN_PASSWORD_LENGTH} caracteres.`;
  if (password !== confirm) return "As duas senhas não são iguais.";
  return null;
}

interface LoginProps {
  api: Api;
  onLoggedIn: (token: string, remember: boolean) => void;
  /** Last health check: false means the server did not answer it. */
  online?: boolean;
  /** The credentials are being checked (the ring shows "pensando" meanwhile). */
  onBusyChange?: (busy: boolean) => void;
  /** Whether this screen makes the first account (so the frame around it says so too). */
  onFirstAccount?: (firstAccount: boolean) => void;
}

/** What the screen is for: signing in, or making the first account ("Primeira vez? Configurar"). */
type Mode = "entrar" | "criar";

/** Whether signing in here should last past closing the window: the installed phone app, or the
 * Visão on this very machine (the Mac app opens http://127.0.0.1). */
export function staysSignedIn(hostname: string, standalone: boolean): boolean {
  return standalone || hostname === "127.0.0.1" || hostname === "localhost" || hostname === "[::1]";
}

export function Login({ api, onLoggedIn, online = true, onBusyChange, onFirstAccount }: LoginProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // No checkbox, as in the mockup: the installed app keeps you signed in (the phone's standalone
  // app, and the Mac app, which opens the server on this very machine); a browser tab on a server
  // elsewhere forgets you when it closes.
  const [remember] = useState(() => staysSignedIn(window.location?.hostname ?? "", window.matchMedia?.("(display-mode: standalone)").matches ?? false));
  const [error, setError] = useState<LoginError | null>(null);
  const [missing, setMissing] = useState<MissingField | null>(null);
  const [busy, setBusy] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  // On the owner's machine with nobody signed up, the server lets this screen make the first account.
  const [firstRunOpen, setFirstRunOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("entrar");
  const [forgot, setForgot] = useState(false);
  const [confirm, setConfirm] = useState("");
  const pending = useRef<AbortController | null>(null);
  const firstRun = mode === "criar" && firstRunOpen;

  useEffect(() => {
    const controller = new AbortController();
    api.firstRunNeeded(controller.signal).then(
      (open) => {
        setFirstRunOpen(open);
        if (open) setMode("criar");
      },
      () => setFirstRunOpen(false),
    );
    return () => controller.abort();
  }, [api]);

  // Leaving the screen mid-request cancels it instead of logging in behind the user's back.
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => onBusyChange?.(busy), [busy, onBusyChange]);
  useEffect(() => onFirstAccount?.(mode === "criar"), [mode, onFirstAccount]);

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setMissing(null);
    setForgot(false);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const empty = missingField(email, password);
    setMissing(empty);
    if (empty) {
      setError(null);
      document.getElementById(empty.field === "email" ? "login-email" : "login-password")?.focus();
      return;
    }
    if (firstRun) {
      const problem = firstRunProblem(password, confirm);
      if (problem) {
        setError({ text: problem, credentials: true });
        return;
      }
    }
    const controller = new AbortController();
    pending.current = controller;
    const timer = window.setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), LOGIN_TIMEOUT_MS);
    setBusy(true);
    setError(null);
    try {
      const token = firstRun
        ? await api.firstRun(email.trim(), password, controller.signal)
        : await api.login(email.trim(), password, controller.signal);
      if (!controller.signal.aborted) onLoggedIn(token, firstRun || remember);
    } catch (e) {
      const reason: unknown = controller.signal.aborted ? controller.signal.reason : e;
      // An abort that is not the timeout means the screen went away: nothing left to tell.
      if (!controller.signal.aborted || (reason instanceof DOMException && reason.name === "TimeoutError")) {
        setError(firstRun && reason instanceof ApiError && reason.status === 422 && reason.message ? { text: reason.message, credentials: true } : loginError(reason));
      }
    } finally {
      window.clearTimeout(timer);
      if (pending.current === controller) pending.current = null;
      setBusy(false);
    }
  }

  function edit(setter: (value: string) => void, value: string, field?: MissingField["field"]) {
    setter(value);
    // The message was about what was typed before; once it changes, it no longer applies.
    if (error?.credentials) setError(null);
    if (field && missing?.field === field) setMissing(null);
  }

  function watchCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState?.("CapsLock") ?? false);
  }

  const fieldError = error?.credentials ? "erro" : undefined;
  const describedBy = error ? "login-error" : undefined;
  const emailMissing = missing?.field === "email";
  const passwordMissing = missing?.field === "password";

  // "Primeira vez? Configurar" away from the owner's machine, or once there is an account: the
  // screen cannot make it, so it says where it is made instead.
  if (mode === "criar" && !firstRunOpen) {
    return (
      <div className="login login--fora">
        <p className="login-aviso" role="status">
          Esta tela não cria a conta aqui: o servidor já tem conta, ou você não está na máquina dele. No servidor, rode{" "}
          <code>python -m apps.api.cli create-user --email seu@email</code>. Depois de entrar, ele te guia em quatro passos.
        </p>
        <div className="login-links">
          <button type="button" className="login-link" onClick={() => switchMode("entrar")}>
            Voltar para entrar
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className="login" onSubmit={submit} aria-busy={busy} noValidate>
      {firstRun && (
        <p className="login-aviso" role="status">
          Primeira vez nesta máquina: crie a sua conta. Ela fica só aqui, e a senha precisa de {MIN_PASSWORD_LENGTH} caracteres ou mais.
        </p>
      )}
      {!online && !error && (
        <p className="login-aviso" role="status">
          O servidor não respondeu à última verificação. Você pode tentar mesmo assim.
        </p>
      )}
      <fieldset className="login-credentials" aria-label="Dados de acesso">
        <div className="rs-campo" data-estado={fieldError || (emailMissing ? "erro" : undefined)}>
          <label htmlFor="login-email">E-mail</label>
          <input
            id="login-email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="voce@exemplo.com"
            maxLength={254}
            value={email}
            onChange={(e) => edit(setEmail, e.target.value, "email")}
            aria-invalid={error?.credentials || emailMissing || undefined}
            aria-describedby={[describedBy, emailMissing ? "login-email-falta" : undefined].filter(Boolean).join(" ") || undefined}
            required
          />
          {emailMissing && (
            <small id="login-email-falta" role="alert">
              {missing?.text}
            </small>
          )}
        </div>
        <div className="rs-campo" data-estado={fieldError || (passwordMissing ? "erro" : undefined)}>
          <label htmlFor="login-password">Senha</label>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete={firstRun ? "new-password" : "current-password"}
            placeholder="Sua senha"
            maxLength={1024}
            value={password}
            onChange={(e) => edit(setPassword, e.target.value, "password")}
            onKeyDown={watchCapsLock}
            onKeyUp={watchCapsLock}
            onBlur={() => setCapsLock(false)}
            aria-invalid={error?.credentials || passwordMissing || undefined}
            aria-describedby={
              [describedBy, passwordMissing ? "login-senha-falta" : undefined, capsLock ? "login-caps" : undefined].filter(Boolean).join(" ") || undefined
            }
            required
          />
          {passwordMissing && (
            <small id="login-senha-falta" role="alert">
              {missing?.text}
            </small>
          )}
          {capsLock && <small id="login-caps">Caps Lock está ligado.</small>}
        </div>
        {firstRun && (
          <div className="rs-campo" data-estado={fieldError}>
            <label htmlFor="login-confirm">Repita a senha</label>
            <input
              id="login-confirm"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              maxLength={1024}
              value={confirm}
              onChange={(e) => edit(setConfirm, e.target.value)}
              aria-invalid={error?.credentials || undefined}
              aria-describedby={describedBy}
              required
            />
          </div>
        )}
      </fieldset>
      {error && (
        <p id="login-error" className="login-erro" role="alert">
          {error.text}
        </p>
      )}
      <button type="submit" className="login-entrar" disabled={busy}>
        {busy ? (
          <>
            <span className="login-pulso" aria-hidden="true" />
            {firstRun ? "Criando…" : "Entrando…"}
          </>
        ) : firstRun ? (
          "Criar minha conta"
        ) : (
          "Entrar"
        )}
      </button>
      {!firstRun && (
        <>
          <div className="login-links">
            <button type="button" className="login-link" aria-expanded={forgot} aria-controls="login-esqueci" onClick={() => setForgot((open) => !open)}>
              Esqueci a senha
            </button>
            <button type="button" className="login-link" onClick={() => switchMode("criar")}>
              Primeira vez? Configurar
            </button>
          </div>
          {forgot && (
            <p id="login-esqueci" className="login-aviso" role="status">
              A senha é trocada no servidor: rode <code>python -m apps.api.cli set-password --email seu@email</code>. Isso encerra os logins abertos.
            </p>
          )}
        </>
      )}
    </form>
  );
}
