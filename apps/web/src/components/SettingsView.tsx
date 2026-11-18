import { currentPosition, locationOn, setLocationOn } from "../location";
import { useEffect, useState } from "react";

import type { Api } from "../api";
import { AccountPanel } from "./AccountPanel";
import { GoogleSettings } from "./GoogleSettings";
import { PushToggle } from "./PushToggle";
import { Setting } from "./Setting";
import { FORCED_THEME, loadThemePreference, saveThemePreference, type ThemePreference } from "../brand/theme";

const THEMES: { value: ThemePreference; label: string }[] = [
  { value: "light", label: "Claro" },
  { value: "dark", label: "Escuro" },
  { value: "system", label: "Sistema" },
];

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
  voiceApproval: boolean;
  onToggleVoiceApproval: () => void;
}

/** All the switches in one place, grouped by what they touch. */
export function SettingsView(props: SettingsViewProps) {
  const { api, onError } = props;
  const [paused, setPaused] = useState<boolean | null>(null);
  const [autoResearch, setAutoResearch] = useState<boolean | null>(null);
  const [morning, setMorning] = useState<boolean | null>(null);
  const [morningNote, setMorningNote] = useState("");
  const [here, setHere] = useState(locationOn());
  const [hereNote, setHereNote] = useState("");
  const [theme, setTheme] = useState<ThemePreference>(loadThemePreference);

  useEffect(() => {
    Promise.all([api.autonomy(), api.permissions()])
      .then(([auto, perms]) => {
        setPaused(auto.paused);
        setAutoResearch(perms.auto_research);
        setMorning(perms.morning_briefing ?? true);
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

  async function toggleMorning() {
    try {
      setMorning((await api.setMorningBriefing(!morning)).morning_briefing ?? !morning);
    } catch (e) {
      onError(e);
    }
  }

  async function morningNow() {
    try {
      const { queued } = await api.briefingNow();
      setMorningNote(queued ? "Pedido. Chega na conversa em alguns segundos." : "A autonomia está pausada.");
    } catch (e) {
      onError(e);
    }
  }

  async function toggleHere() {
    if (here) {
      setLocationOn(false);
      setHere(false);
      setHereNote("");
      return;
    }
    // Asks the permission now, while the owner is looking, not in the middle of a question.
    const position = await currentPosition(10_000);
    if (!position) {
      setHereNote("O navegador não deixou. No iPhone: Ajustes > Privacidade > Serviços de Localização > Safari (ou o app) > Ao Usar.");
      return;
    }
    setLocationOn(true);
    setHere(true);
    setHereNote("");
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
        <h1 id="settings-title">Ajustes</h1>
        <p className="lede">Voz, avisos, permissões e conta.</p>
      </header>
      <div className="page-body settings">
        {!FORCED_THEME && (
        <section className="settings-group" aria-labelledby="g-aparencia">
          <h2 id="g-aparencia" className="rotulo">Aparência</h2>
          <div className="setting">
            <div className="setting-text">
              <span id="theme-title" className="setting-title">Tema</span>
              <p className="note">Claro é o padrão. “Sistema” segue o claro ou escuro do aparelho.</p>
            </div>
            <div className="segmented" role="radiogroup" aria-labelledby="theme-title">
              {THEMES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  role="radio"
                  aria-checked={theme === t.value}
                  onClick={() => { setTheme(t.value); saveThemePreference(t.value); }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </section>
        )}
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
          <Setting
            title="Resumo da manhã"
            description="Quando o horário silencioso acaba: agenda do dia, painéis conferidos na hora, o que espera seu sim e o que eu estudei. Sem nada novo, não mando."
            checked={morning === true}
            disabled={morning === null || paused === true}
            onChange={() => void toggleMorning()}
          >
            {morning && paused === false && (
              <button type="button" className="link-button" onClick={() => void morningNow()}>Mandar agora</button>
            )}
            {morningNote && <p className="note">{morningNote}</p>}
          </Setting>
        </section>

        <section className="settings-group" aria-labelledby="g-local">
          <h2 id="g-local" className="rotulo">Localização</h2>
          <Setting
            title="Usar minha localização"
            description="Só quando você pergunta de algo perto (“tem farmácia aberta aqui perto?”). Vai só com essa mensagem, nunca fica guardada e o modelo não vê as coordenadas. Vale só neste aparelho."
            checked={here}
            onChange={() => void toggleHere()}
          >
            {hereNote && <p className="note">{hereNote}</p>}
          </Setting>
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
