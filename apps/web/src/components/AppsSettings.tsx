import { useEffect, useState } from "react";

import type { Api, AppCatalogItem, AppsState } from "../api";
import { searchCatalog } from "../apps";
import { confirmar, perguntar } from "../ask";
import { Setting } from "./Setting";

/**
 * Ajustes › Apps (docs/APPS.md): the owner's other apps through Composio. Hidden when the server
 * has no Composio key. Says plainly that the connection lives on Composio, not here.
 */
export function AppsSettings({ api, onError }: { api: Api; onError: (e: unknown) => void }) {
  const [state, setState] = useState<AppsState | null>(null);
  const [catalog, setCatalog] = useState<AppCatalogItem[] | null>(null);
  const [query, setQuery] = useState("");
  const [waiting, setWaiting] = useState<string | null>(null);
  // When the browser blocked the new tab: the page to open with a tap of the owner's own.
  const [link, setLink] = useState<string | null>(null);
  // "Olhar sozinho": the app whose read is being chosen right now, and why it could not be.
  const [choosing, setChoosing] = useState<string | null>(null);
  const [glanceNote, setGlanceNote] = useState<{ toolkit: string; text: string } | null>(null);

  useEffect(() => {
    api.apps().then(setState).catch(onError);
  }, [api, onError]);

  async function openCatalog() {
    try {
      setCatalog(await api.appsCatalog());
    } catch (e) {
      onError(e);
    }
  }

  async function connect(app: AppCatalogItem) {
    // Opened on the tap itself, so the browser does not block it; the address comes after.
    // Blocked anyway: a link to tap, never leaving this page (the wait below would stop).
    const tab = window.open("", "_blank");
    setWaiting(app.name);
    try {
      const started = await api.appsConnect(app.slug);
      if (tab) tab.location.href = started.url;
      else setLink(started.url);
      setState(await api.appsWait(started.connection_id));
      setCatalog(null);
      setQuery("");
    } catch (e) {
      tab?.close();
      onError(e);
    } finally {
      setWaiting(null);
      setLink(null);
    }
  }

  async function disconnect(slug: string, name: string) {
    if (!(await confirmar(`Desconectar o ${name}? A conexão é revogada e apagada no Composio, e o que esperava sua aprovação nele é recusado.`, "Desconectar"))) return;
    try {
      await api.appsDisconnect(slug);
      setState(await api.apps());
    } catch (e) {
      onError(e);
    }
  }

  async function togglePayments(slug: string, name: string, on: boolean) {
    try {
      if (!on) {
        setState(await api.appsPayments(slug, false));
        return;
      }
      const cap = await perguntar(`Até quanto, em reais, eu posso pagar pelo ${name} num dia?`, "200", "Ligar");
      if (cap === null) return;
      setState(await api.appsPayments(slug, true, cap, "BRL"));
    } catch (e) {
      onError(e);
    }
  }

  async function toggleGlance(slug: string, on: boolean) {
    setChoosing(slug);
    setGlanceNote(null);
    try {
      await api.appsGlance(slug, on);
      setState(await api.apps());
    } catch (e) {
      // The server says in words why it found nothing to read (no read tool, Composio down).
      setGlanceNote({ toolkit: slug, text: e instanceof Error ? e.message : "Não deu para ligar agora." });
    } finally {
      setChoosing(null);
    }
  }

  if (!state?.enabled) return null;
  const connected = new Set(state.connected.map((a) => a.toolkit));
  const found = catalog ? searchCatalog(catalog.filter((a) => !connected.has(a.slug)), query) : [];
  return (
    <section className="settings-group" aria-labelledby="g-apps">
      <h2 id="g-apps" className="rotulo">Apps</h2>
      <div className="setting">
        <div className="setting-text">
          <span className="setting-title">Outros apps</span>
          <p className="note">
            Notion, GitHub, Slack e muitos outros, pelo Composio. Leio quando você pergunta; mudar qualquer coisa só com o seu Aprovar.
            Apagar fica desligado. Email e agenda continuam pelo Google, acima.
          </p>
          <p className="note">{state.notice}</p>
          {state.problem && <p className="error">{state.problem}</p>}
          <p className="note">
            Este mês: {state.calls_this_month} de {state.monthly_limit} chamadas.
          </p>
        </div>
      </div>
      {state.connected.map((a) => (
        <div key={a.toolkit}>
          <div className="setting">
            <div className="setting-text">
              <span className="setting-title">{a.name}</span>
              <p className="note">Conectado pelo Composio.</p>
            </div>
            <button type="button" className="ghost" onClick={() => void disconnect(a.toolkit, a.name)}>Desconectar</button>
          </div>
          <Setting
            title={`Olhar o ${a.name} sozinho`}
            description={
              a.glance
                ? `A cada 3 horas eu olho: ${a.glance}. Só leio, e só te chamo se algo pedir sua atenção.`
                : "De tempos em tempos eu olho o que é novo aqui e te aviso do que importa. Só leio."
            }
            checked={Boolean(a.glance)}
            disabled={choosing !== null}
            onChange={() => void toggleGlance(a.toolkit, !a.glance)}
          >
            {choosing === a.toolkit && <p className="note">Escolhendo o que olhar no {a.name}…</p>}
            {glanceNote?.toolkit === a.toolkit && <p className="error">{glanceNote.text}</p>}
          </Setting>
          {(a.payment_app || a.payments) && (
            <Setting
              title={`Pagamentos pelo ${a.name}`}
              description={
                a.payments
                  ? `Até ${a.payments.currency} ${a.payments.cap} por dia. Cada pagamento mostra o valor e para quem, e só sai com um toque seu confirmando o valor; pela voz, nunca.`
                  : "Desligado: eu nunca preparo pagamentos aqui. Ligado, com um teto por dia, cada um ainda espera o seu toque confirmando o valor."
              }
              checked={Boolean(a.payments)}
              onChange={() => void togglePayments(a.toolkit, a.name, !a.payments)}
            />
          )}
        </div>
      ))}
      {waiting ? (
        <div className="setting">
          <p className="note">
            {link ? (
              <>O navegador não abriu a página sozinho. <a href={link} target="_blank" rel="noopener noreferrer">Abrir a página do Composio para entrar no {waiting}</a>; espero você terminar lá.</>
            ) : (
              <>Esperando você terminar de entrar no {waiting}, na página do Composio que abriu…</>
            )}
          </p>
        </div>
      ) : catalog === null ? (
        <div className="setting">
          <div className="setting-text">
            <span className="setting-title">Conectar um app</span>
          </div>
          <button type="button" className="ghost" onClick={() => void openCatalog()}>Ver os apps</button>
        </div>
      ) : (
        <div className="setting apps-catalog">
          <div className="setting-text">
            <label className="setting-title" htmlFor="apps-search">Conectar um app</label>
            <input
              id="apps-search"
              className="settings-search"
              type="search"
              placeholder="Procurar (Notion, Linear, Trello…)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <ul className="apps-list">
              {found.map((a) => (
                <li key={a.slug}>
                  <div>
                    <strong>{a.name}</strong>
                    {a.description && <p className="note">{a.description}</p>}
                    {a.asks_key && <p className="note">Na conexão, a página do Composio pede a sua chave de API desse app; ela fica guardada lá.</p>}
                    {!a.connectable && <p className="note">Pede um app OAuth próprio no Composio; ainda não dá para conectar daqui.</p>}
                  </div>
                  <button type="button" className="ghost" disabled={!a.connectable} onClick={() => void connect(a)}>Conectar</button>
                </li>
              ))}
              {!found.length && <li className="note">Nenhum app com esse nome.</li>}
            </ul>
          </div>
        </div>
      )}
    </section>
  );
}
