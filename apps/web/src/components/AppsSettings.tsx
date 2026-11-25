import { useEffect, useState } from "react";

import type { Api, AppCatalogItem, AppsState } from "../api";
import { searchCatalog } from "../apps";

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
    if (!window.confirm(`Desconectar o ${name}? A conexão é revogada e apagada no Composio, e o que esperava sua aprovação nele é recusado.`)) return;
    try {
      await api.appsDisconnect(slug);
      setState(await api.apps());
    } catch (e) {
      onError(e);
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
        <div className="setting" key={a.toolkit}>
          <div className="setting-text">
            <span className="setting-title">{a.name}</span>
            <p className="note">Conectado pelo Composio.</p>
          </div>
          <button type="button" className="ghost" onClick={() => void disconnect(a.toolkit, a.name)}>Desconectar</button>
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
