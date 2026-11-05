import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  type Api,
  type OnboardingAnswers,
  type OnboardingResult,
  type OnboardingStatus,
} from "../api";

const POINTS = [
  ["Lembra de você", "Se você ligar a memória, guarda entre conversas o que for útil sobre você."],
  ["Pensa e estuda entre conversas", "Um processo roda em segundo plano, chama o modelo e parte do que vocês conversaram. Estudar sozinho só com a sua permissão."],
  ["Puxa conversa", "Pode mandar mensagem sem você pedir. Fica quieto no horário silencioso e para se você não responder."],
  ["Aprende com correções", "Quando você corrige o jeito dele, isso vira uma regra curta para as próximas conversas."],
  ["Você vê e desfaz", "Em Estudos ficam as anotações, os pensamentos e os estudos. Anotações e autodescrição dá para desfazer; anotações, também apagar."],
];

const QUESTIONS: Array<{ key: keyof OnboardingAnswers; label: string; hint: string }> = [
  { key: "who", label: "Quem é você?", hint: "Nome, como prefere ser chamado, o que quiser contar." },
  { key: "work", label: "No que você trabalha?", hint: "Profissão, projetos, o que ocupa seus dias." },
  { key: "goal", label: "O que você quer dele?", hint: "Pensar junto, acompanhar um projeto, lembrar das coisas." },
  { key: "tone", label: "Como prefere que ele fale com você?", hint: "Direto, curto, com exemplos, sem formalidade." },
];

type Permission = "memory" | "study" | "research";
type Permissions = Record<Permission, boolean>;

const TOGGLES: Array<{ key: Permission; label: string; detail: string }> = [
  { key: "memory", label: "Memória entre conversas", detail: "Guarda informações selecionadas e as suas respostas daqui. Desligada, nada disso fica." },
  { key: "study", label: "Estudo autônomo", detail: "Estuda temas ligados a você entre as conversas, dentro do orçamento. Cada rodada fica em Estudos." },
  { key: "research", label: "Pesquisa autônoma", detail: "Dúvidas de fatos públicos que ficaram sem resposta são pesquisadas de novo, sem pedir aprovação a cada vez." },
];

const NO_ANSWERS: OnboardingAnswers = { who: "", work: "", goal: "", tone: "" };

function closingNotice(result: OnboardingResult): string | null {
  if (result.saved.length > 0) {
    return "Suas respostas foram para as anotações dele. Em Estudos você vê, desfaz ou apaga.";
  }
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

/** The first run: how he works, a few questions and the permissions. Shown once, always skippable. */
export function Onboarding({ api, status, onMemoryChange, onError, onDone }: Props) {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<OnboardingAnswers>(NO_ANSWERS);
  const [permissions, setPermissions] = useState<Permissions | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState<Permission | "finish" | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const wrote = Object.values(answers).some((value) => value.trim());
  const busy = saving !== null;

  useEffect(() => heading.current?.focus(), [step]);

  const fail = useCallback((e: unknown, prefix: string) => {
    if (e instanceof ApiError && e.status === 401) onError(e);
    else setFailure(`${prefix}${message(e)}`);
  }, [onError]);

  const loadPermissions = useCallback(async () => {
    setLoadFailed(false);
    try {
      const [memory, study, autonomy] = await Promise.all([
        api.memorySettings(), api.study(), api.permissions(),
      ]);
      setPermissions({ memory: memory.enabled, study: study.enabled, research: autonomy.auto_research });
    } catch (e) {
      setLoadFailed(true);
      fail(e, "Não deu para ler as permissões: ");
    }
  }, [api, fail]);

  useEffect(() => {
    if (step === 3 && !permissions) void loadPermissions();
  }, [step, permissions, loadPermissions]);

  function go(next: number) {
    setFailure(null);
    setStep(next);
  }

  async function toggle(key: Permission) {
    if (!permissions) return;
    const next = !permissions[key];
    setSaving(key);
    setFailure(null);
    try {
      const applied = key === "memory"
        ? (await api.setMemoryEnabled(next)).enabled
        : key === "study"
          ? (await api.setStudyEnabled(next)).enabled
          : (await api.setAutoResearch(next)).auto_research;
      setPermissions({ ...permissions, [key]: applied });
      if (key === "memory") onMemoryChange(applied);
    } catch (e) {
      fail(e, "Não deu para mudar, continua como estava: ");
    } finally {
      setSaving(null);
    }
  }

  async function finish() {
    setSaving("finish");
    setFailure(null);
    try {
      onDone(closingNotice(await api.finishOnboarding(answers)));
    } catch (e) {
      // A refusal is about the answers: go back to them, with the text intact.
      if (e instanceof ApiError && e.status === 422) setStep(2);
      fail(e, "");
    } finally {
      setSaving(null);
    }
  }

  async function skipAll() {
    setSaving("finish");
    setFailure(null);
    try {
      onDone(closingNotice(await api.skipOnboarding()));
    } catch (e) {
      fail(e, "Não deu para pular: ");
    } finally {
      setSaving(null);
    }
  }

  function skipStep() {
    if (step === 3) void finish();
    else {
      if (step === 2) setAnswers(NO_ANSWERS);
      go(step + 1);
    }
  }

  return (
    <section className="onboarding" aria-labelledby="onboarding-title">
      <div className="onboarding-top">
        <span className="eyebrow">PASSO {step} DE 3</span>
        <button type="button" className="ghost" onClick={() => void skipAll()} disabled={busy}>
          {wrote ? "Descartar e pular tudo" : "Pular tudo"}
        </button>
      </div>

      {failure && <p className="error" role="alert">{failure}</p>}

      {step === 1 && <>
        <h1 id="onboarding-title" ref={heading} tabIndex={-1}>Como ele funciona</h1>
        <p className="onboarding-lead">Isto é software: um modelo de linguagem com memória, estudo e iniciativa em volta. Em resumo:</p>
        <ul className="onboarding-points">
          {POINTS.map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}
        </ul>
        {!status.mind_enabled && <p className="note onboarding-status">Nesta instalação a mente está desligada: pensar entre conversas, puxar conversa e usar as anotações nas respostas só funcionam quando ela for ligada.</p>}
      </>}

      {step === 2 && <>
        <h1 id="onboarding-title" ref={heading} tabIndex={-1}>Algumas perguntas</h1>
        <p className="onboarding-lead">Todas opcionais. Só ficam guardadas se a memória estiver ligada no próximo passo. Não escreva senhas nem documentos.</p>
        {QUESTIONS.map((question) => (
          <label className="onboarding-field" key={question.key}>
            <span>{question.label}</span>
            <textarea
              rows={2}
              value={answers[question.key]}
              placeholder={question.hint}
              onChange={(event) => setAnswers({ ...answers, [question.key]: event.target.value })}
            />
          </label>
        ))}
        <p className="note">Espaço livre nas anotações: {status.room.profile} caracteres para quem você é, {status.room.rules} para o jeito de falar. Se já houver algo anotado, as respostas entram depois, sem apagar nada.</p>
      </>}

      {step === 3 && <>
        <h1 id="onboarding-title" ref={heading} tabIndex={-1}>O que ele pode fazer</h1>
        <p className="onboarding-lead">Cada chave vale assim que você muda e aparece como está agora. Depois você muda tudo em Preferências e em Estudos.</p>
        {permissions === null && !loadFailed && <p className="note" role="status">Lendo as permissões…</p>}
        {permissions && TOGGLES.map((item) => (
          <label className="onboarding-toggle" key={item.key}>
            <span>
              <input
                type="checkbox"
                checked={permissions[item.key]}
                disabled={busy}
                onChange={() => void toggle(item.key)}
              />
              {item.label}
            </span>
            <span className="note">{item.detail}</span>
          </label>
        ))}
        {loadFailed && <button type="button" className="ghost" onClick={() => void loadPermissions()}>Tentar ler de novo</button>}
        {permissions && wrote && (
          <p className="note onboarding-status" role="status">
            {permissions.memory
              ? "Memória ligada: suas respostas vão para as anotações dele, e você pode desfazer ou apagar em Estudos."
              : "Memória desligada: nada do que você escreveu será guardado."}
          </p>
        )}
      </>}

      <div className="onboarding-actions">
        {step > 1 && <button type="button" className="ghost" onClick={() => go(step - 1)} disabled={busy}>Voltar</button>}
        <button type="button" className="ghost" onClick={skipStep} disabled={busy}>
          {step === 2 ? "Pular sem responder" : "Pular esta etapa"}
        </button>
        <button
          type="button"
          className="onboarding-next"
          onClick={() => (step === 3 ? void finish() : go(step + 1))}
          disabled={busy}
        >
          {saving === "finish" ? "Salvando…" : step === 3 ? "Concluir" : "Continuar"}
        </button>
      </div>
    </section>
  );
}
