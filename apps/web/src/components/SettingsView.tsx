import { useEffect, useState } from "react";

import type { Api } from "../api";
import { AccountPanel } from "./AccountPanel";
import { GoogleSettings } from "./GoogleSettings";
import { PushToggle } from "./PushToggle";
import { Setting } from "./Setting";

interface SettingsViewProps {
  api: Api;
  memoryEnabled: boolean;
  onToggleMemory: () => void;
  speakReplies: boolean;
  canSpeak: boolean;
  speakerKind: "server" | "device" | null;
  onToggleSpeak: () => void;
  deviceListening: boolean;
  deviceCouldListen: boolean;
  serverListening: boolean;
  onToggleDeviceListening: () => void;
  onRestartOnboarding: () => void;
  onLogout: () => void;
  onError: (e: unknown) => void;
  sky: boolean;
  onToggleSky: () => void;
  voiceApproval: boolean;
  onToggleVoiceApproval: () => void;
}

/** All the switches in one place, grouped by what they touch. */
export function SettingsView(props: SettingsViewProps) {
  const { api, onError } = props;
  const [paused, setPaused] = useState<boolean | null>(null);
  const [autoResearch, setAutoResearch] = useState<boolean | null>(null);

  useEffect(() => {
    Promise.all([api.autonomy(), api.permissions()])
      .then(([auto, perms]) => {
        setPaused(auto.paused);
        setAutoResearch(perms.auto_research);
      })
      .catch(onError);
  }, [api, onError]);

  async function togglePause() {
    try {
      setPaused((await api.setAutonomyPaused(!paused)).paused);
    } catch (e) {
      onError(e);
    }
  }

  async function toggleAutoResearch() {
    try {
      setAutoResearch((await api.setAutoResearch(!autoResearch)).auto_research);
    } catch (e) {
      onError(e);
    }
  }

  return (
    <section className="page" aria-labelledby="settings-title">
      <header className="page-head">
        <span className="rotulo">Ajustes</span>
        <h1 id="settings-title">Do seu <em>jeito.</em></h1>
      </header>
      <div className="page-body settings">
        <section className="settings-group" aria-labelledby="g-aparencia">
          <h2 id="g-aparencia" className="rotulo">Aparência</h2>
          <Setting
            title="Floresta com neblina ao fundo"
            description="Pinheiros com neblina que se mexe, nas cores da hora do dia, com vidro de névoa por cima. Desligado, volta o tema escuro."
            checked={props.sky}
            onChange={props.onToggleSky}
          />
        </section>
        <section className="settings-group" aria-labelledby="g-voz">
          <h2 id="g-voz" className="rotulo">Voz e avisos</h2>
          <Setting
            title="Falar as respostas"
            description={!props.canSpeak ? "Sem voz neste aparelho." : props.speakerKind === "device" ? "Leio em voz alta com a voz do aparelho." : "Leio em voz alta com a voz que escolhi."}
            checked={props.speakReplies}
            disabled={!props.canSpeak}
            onChange={props.onToggleSpeak}
          />
          <Setting
            title="Aprovar por voz na ligação"
            description="Numa ligação, eu leio em voz alta o email, o evento ou o pedido ao Mac e espero você dizer “pode mandar” (ou “não”). Fora da ligação, só com o toque."
            checked={props.voiceApproval}
            onChange={props.onToggleVoiceApproval}
          />
          {!props.serverListening && props.deviceCouldListen && (
            <Setting
              title="Ouvir pelo navegador"
              description="Para me ligar daqui. O navegador pode mandar o áudio ao fabricante (Google no Chrome, Apple no Safari)."
              checked={props.deviceListening}
              onChange={props.onToggleDeviceListening}
            />
          )}
          <PushToggle api={api} onError={onError} />
        </section>

        <section className="settings-group" aria-labelledby="g-autonomia">
          <h2 id="g-autonomia" className="rotulo">Autonomia</h2>
          <Setting
            title="Agir por conta própria"
            description="Pensar, estudar e puxar conversa quando eu tiver algo útil. Desligado, só respondo."
            checked={paused === false}
            disabled={paused === null}
            onChange={() => void togglePause()}
          />
          <Setting
            title="Pesquisar sozinho"
            description="Dúvidas de fatos públicos que ficaram sem resposta, só na Wikipédia e dentro do orçamento."
            checked={autoResearch === true}
            disabled={autoResearch === null || paused === true}
            onChange={() => void toggleAutoResearch()}
          />
        </section>

        <section className="settings-group" aria-labelledby="g-google">
          <h2 id="g-google" className="rotulo">Google</h2>
          <GoogleSettings api={api} onError={onError} />
        </section>

        <section className="settings-group" aria-labelledby="g-memoria">
          <h2 id="g-memoria" className="rotulo">Memória</h2>
          <Setting
            title="Lembrar entre conversas"
            description="Guardo o que você escolher para continuar de onde paramos. O que sei de você fica no Caderno."
            checked={props.memoryEnabled}
            onChange={props.onToggleMemory}
          />
          <div className="setting">
            <div className="setting-text">
              <span className="setting-title">Perguntas iniciais</span>
              <p className="note">Refazer a apresentação do começo, para eu te conhecer de novo.</p>
            </div>
            <button type="button" className="ghost" onClick={props.onRestartOnboarding}>Refazer</button>
          </div>
        </section>

        <section className="settings-group" aria-labelledby="g-conta">
          <h2 id="g-conta" className="rotulo">Conta</h2>
          <AccountPanel api={api} />
          <div className="setting">
            <div className="setting-text">
              <span className="setting-title">Sair deste aparelho</span>
              <p className="note">Os outros continuam conectados.</p>
            </div>
            <button type="button" className="ghost" onClick={props.onLogout}>Sair</button>
          </div>
        </section>
      </div>
    </section>
  );
}
