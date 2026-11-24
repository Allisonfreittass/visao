import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type Api,
  type ArmDevice,
  type BrainMode,
  type BrainState,
  type OnboardingAnswers,
  type OnboardingResult,
  type OnboardingStatus,
  type QuietHours,
} from "../api";
import { Corvo } from "../brand/Corvo";

const QUESTIONS: Array<{ key: keyof OnboardingAnswers; label: string; hint: string }> = [
  { key: "who", label: "Quem é você?", hint: "Nome, como prefere ser chamado, o que quiser contar." },
  { key: "work", label: "No que você trabalha?", hint: "Profissão, projetos, o que ocupa seus dias." },
  { key: "goal", label: "O que você quer dele?", hint: "Pensar junto, acompanhar um projeto, lembrar das coisas." },
  { key: "tone", label: "Como prefere que ele fale com você?", hint: "Direto, curto, com exemplos, sem formalidade." },
];

const NO_ANSWERS: OnboardingAnswers = { who: "", work: "", goal: "", tone: "" };
const STEPS = 4;

function closingNotice(result: OnboardingResult): string | null {
  if (result.saved.length > 0) return "Suas respostas foram para as anotações dele. No Caderno você vê, desfaz ou apaga.";
  if (result.discarded) return "Nada do que você escreveu foi guardado: a memória estava desligada.";
  return null;
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

interface Props {
  api: Api;
  status: OnboardingStatus;
  onMemoryChange: (enabled: boolean) => void;
  onError: (e: unknown) => void;
  onDone: (notice: string | null) => void;
}

/** One choice of a step: a card with a title and a line under it. */
function Choice({ checked, title, note, disabled, onPick }: { checked: boolean; title: string; note: string; disabled?: boolean; onPick: () => void }) {
  return (
    <button type="button" role="radio" aria-checked={checked} className="choice-card" disabled={disabled} onClick={onPick}>
      <span className="choice-card-title">{title}</span>
      <span className="choice-card-note">{note}</span>
    </button>
  );
}

/** The first run, in four steps (who answers, memory, the Mac, when he may talk). Each choice
 * applies at once; every step can be skipped, and so can the whole thing. */
export function Onboarding({ api, status, onMemoryChange, onError, onDone }: Props) {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<OnboardingAnswers>(NO_ANSWERS);
  const [brain, setBrain] = useState<BrainState | null>(null);
  const [memory, setMemory] = useState<boolean | null>(null);
  const [study, setStudy] = useState<boolean | null>(null);
  const [research, setResearch] = useState<boolean | null>(null);
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  const [pairing, setPairing] = useState<ArmDevice | null>(null);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const wrote = Object.values(answers).some((value) => value.trim());

  useEffect(() => heading.current?.focus(), [step]);

  const fail = useCallback((e: unknown, prefix: string) => {
    if (e instanceof ApiError && e.status === 401) onError(e);
    else setFailure(`${prefix}${message(e)}`);
  }, [onError]);

  useEffect(() => {
    api.brain().then(setBrain, () => undefined);
    api.memorySettings().then((m) => setMemory(m.enabled), () => undefined);
    api.study().then((s) => setStudy(s.enabled), () => undefined);
    api.permissions().then((p) => setResearch(p.auto_research), () => undefined);
    api.quietHours().then(setQuiet, () => undefined);
  }, [api]);

  async function apply<T>(action: () => Promise<T>, then: (value: T) => void) {
    setFailure(null);
    try {
      then(await action());
    } catch (e) {
      fail(e, "Não deu para mudar, continua como estava: ");
    }
  }

  const chooseBrain = (mode: BrainMode) => apply(() => api.setBrain(mode), setBrain);
  const chooseMemory = (on: boolean) => apply(() => api.setMemoryEnabled(on), (r) => { setMemory(r.enabled); onMemoryChange(r.enabled); });

  async function finish() {
    setSaving(true);
    setFailure(null);
    try {
      onDone(closingNotice(await api.finishOnboarding(answers)));
    } catch (e) {
      // A refusal is about the answers: go back to them, with the text intact.
      if (e instanceof ApiError && e.status === 422) setStep(2);
      fail(e, "");
    } finally {
      setSaving(false);
    }
  }

  async function skipAll() {
    setSaving(true);
    setFailure(null);
    try {
      onDone(closingNotice(await api.skipOnboarding()));
    } catch (e) {
      fail(e, "Não deu para pular: ");
    } finally {
      setSaving(false);
    }
  }

  function go(next: number) {
    setFailure(null);
    setStep(next);
  }

  return (
    <section className="onboarding-novo" aria-labelledby="onboarding-title">
      <div className="onboarding-marca">
        <Corvo size={260} className="onboarding-corvo" />
        <ol className="onboarding-progress" aria-label={`Passo ${step} de ${STEPS}`}>
          {Array.from({ length: STEPS }, (_, i) => <li key={i} data-done={i < step || undefined} />)}
        </ol>
      </div>
      <div className="onboarding-corpo">
        <div className="onboarding-top">
          <span className="onboarding-step">Passo {step} de {STEPS}</span>
          <button type="button" className="link-button" onClick={() => void skipAll()} disabled={saving}>
            {wrote ? "Descartar e pular tudo" : "Pular tudo"}
          </button>
        </div>
        {failure && <p className="error" role="alert">{failure}</p>}

        {step === 1 && <>
          <h1 id="onboarding-title" ref={heading} tabIndex={-1}>Quem responde?</h1>
          <p className="onboarding-lead">Escolha quem pensa as respostas. Dá para trocar depois, no rodapé da janela ou pedindo no chat.</p>
          <div className="onboarding-choices" role="radiogroup" aria-labelledby="onboarding-title">
            <Choice checked={brain?.mode === "nuvem"} title="Nuvem" note="Melhor qualidade · paga por uso" onPick={() => void chooseBrain("nuvem")} />
            <Choice
              checked={brain?.mode === "local"}
              title={brain?.local_model ? `${brain.local_model} · no seu Mac` : "No seu Mac"}
              note={brain?.mac_online ? "Grátis e privado · mais lento" : "Precisa do Mac conectado (passo 3)"}
              disabled={!brain?.mac_online}
              onPick={() => void chooseBrain("local")}
            />
            <Choice checked={brain?.mode === "auto"} title="Automático" note="Nuvem, e o Mac se ela falhar" onPick={() => void chooseBrain("auto")} />
          </div>
          {!status.mind_enabled && <p className="note">Nesta instalação a mente está desligada: pensar entre conversas e puxar conversa só funcionam quando ela for ligada.</p>}
        </>}

        {step === 2 && <>
          <h1 id="onboarding-title" ref={heading} tabIndex={-1}>O que ele pode lembrar?</h1>
          <p className="onboarding-lead">Ele só guarda o que você deixar, e sempre mostra de onde veio cada lembrança.</p>
          <div className="onboarding-choices" role="radiogroup" aria-labelledby="onboarding-title">
            <Choice checked={memory === true} title="Lembrar entre conversas" note="Recomendado · tudo aparece no Caderno" onPick={() => void chooseMemory(true)} />
            <Choice checked={memory === false} title="Não guardar nada" note="Cada conversa começa do zero" onPick={() => void chooseMemory(false)} />
          </div>
          {memory && (
            <details className="onboarding-questions">
              <summary>Contar um pouco de você (opcional)</summary>
              <p className="note">Não escreva senhas nem documentos.</p>
              {QUESTIONS.map((question) => (
                <label className="onboarding-field" key={question.key}>
                  <span>{question.label}</span>
                  <textarea rows={2} value={answers[question.key]} placeholder={question.hint} onChange={(event) => setAnswers({ ...answers, [question.key]: event.target.value })} />
                </label>
              ))}
            </details>
          )}
        </>}

        {step === 3 && <>
          <h1 id="onboarding-title" ref={heading} tabIndex={-1}>Conectar o seu Mac?</h1>
          <p className="onboarding-lead">Com o Braço, ele roda testes e mexe em arquivos dos projetos que você liberar, sempre pedindo aprovação antes.</p>
          {pairing?.token ? (
            <div className="onboarding-pair">
              <p className="note">Cole este token em <code>~/.config/visao/braco.json</code> e rode no Mac:</p>
              <pre>bash arm/instalar-mac.sh</pre>
              <code className="mac-token">{pairing.token}</code>
              <p className="note">O token não aparece de novo.</p>
            </div>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => void apply(() => api.pairArm("Mac"), setPairing)}>Gerar o token do Mac</button>
          )}
          <p className="note">Pode pular: dá para conectar depois em Mac.</p>
        </>}

        {step === 4 && <>
          <h1 id="onboarding-title" ref={heading} tabIndex={-1}>Quando ele pode falar com você?</h1>
          <p className="onboarding-lead">Fora do silêncio, ele pode puxar conversa quando tiver algo útil. Dentro dele, nada chega.</p>
          {quiet && (
            <div className="quiet-hours" role="group" aria-label="Horário de silêncio">
              <label>Silêncio das <input type="time" value={quiet.quiet_start} onChange={(e) => e.target.value && void apply(() => api.setQuietHours({ ...quiet, quiet_start: e.target.value }), setQuiet)} /></label>
              <label>às <input type="time" value={quiet.quiet_end} onChange={(e) => e.target.value && void apply(() => api.setQuietHours({ ...quiet, quiet_end: e.target.value }), setQuiet)} /></label>
            </div>
          )}
          <div className="onboarding-switches">
            {study !== null && (
              <label className="onboarding-toggle">
                <input type="checkbox" checked={study} onChange={() => void apply(() => api.setStudyEnabled(!study), (r) => setStudy(r.enabled))} />
                <span>Estudar entre conversas<span className="note"> · temas ligados a você, dentro do orçamento</span></span>
              </label>
            )}
            {research !== null && (
              <label className="onboarding-toggle">
                <input type="checkbox" checked={research} onChange={() => void apply(() => api.setAutoResearch(!research), (r) => setResearch(r.auto_research))} />
                <span>Pesquisar sozinho<span className="note"> · dúvidas de fatos públicos, sempre com fonte</span></span>
              </label>
            )}
          </div>
        </>}

        <div className="onboarding-actions-novo">
          {step > 1 && <button type="button" className="btn-secondary" onClick={() => go(step - 1)} disabled={saving}>Voltar</button>}
          <button type="button" className="btn-primary" onClick={() => (step === STEPS ? void finish() : go(step + 1))} disabled={saving}>
            {saving ? "Salvando…" : step === STEPS ? "Começar" : "Continuar"}
          </button>
        </div>
      </div>
    </section>
  );
}
