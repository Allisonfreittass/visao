// The device's own speech engines, used when the server has no voice models (the cloud build):
// it lets a call work from the phone anywhere. Synthesis runs on the device. Recognition may send
// the audio to the browser maker (Google in Chrome, Apple in Safari), so it is used only after the
// owner turns it on, and the interface says so.

import { speakableText } from "../speech/speakable";

// The Web Speech API ships unprefixed in some browsers and prefixed in others, and TypeScript's
// DOM types do not include recognition at all.
interface RecognitionAlternative { transcript: string }
interface RecognitionResult { isFinal: boolean; 0: RecognitionAlternative; length: number }
interface RecognitionEvent { resultIndex: number; results: ArrayLike<RecognitionResult> }
interface RecognitionErrorEvent { error: string }
interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: RecognitionErrorEvent) => void) | null;
  onspeechstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionConstructor = new () => Recognition;

function recognitionClass(): RecognitionConstructor | null {
  const scope = globalThis as unknown as {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export function browserCanListen(): boolean {
  return recognitionClass() !== null;
}

export function browserCanSpeak(): boolean {
  return typeof globalThis.speechSynthesis !== "undefined";
}

/** Prefers a Brazilian voice that runs on the device; falls back to any pt voice, then default. */
export function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const pt = voices.filter((v) => v.lang.toLowerCase().startsWith("pt"));
  const br = pt.filter((v) => v.lang.toLowerCase().replace("_", "-") === "pt-br");
  return (
    br.find((v) => v.localService) ?? br[0] ?? pt.find((v) => v.localService) ?? pt[0] ?? null
  );
}

/** Same surface as the server Speaker, so the app does not care which one talks. */
export class BrowserSpeaker {
  private active = false;
  private startedAt = 0;

  get speaking(): boolean {
    return this.active;
  }

  unlock(): void {
    // iOS only lets speech start inside a gesture: an empty utterance opens the gate.
    if (!browserCanSpeak()) return;
    const warmup = new SpeechSynthesisUtterance("");
    warmup.volume = 0;
    speechSynthesis.speak(warmup);
  }

  /** No audio tap exists for device speech: a soft pulse stands in for the level. */
  level(): number {
    if (!this.active) return 0;
    const t = (performance.now() - this.startedAt) / 1000;
    return 0.35 + 0.25 * Math.abs(Math.sin(t * 5.3) * Math.sin(t * 1.7));
  }

  speak(text: string, onFirstAudio?: (ms: number) => void): Promise<"completed" | "aborted"> {
    this.stop();
    const spoken = speakableText(text);
    if (!browserCanSpeak() || !spoken) return Promise.resolve("completed");
    const requested = performance.now();
    return new Promise((resolve) => {
      const utterance = new SpeechSynthesisUtterance(spoken);
      utterance.lang = "pt-BR";
      const voice = pickVoice(speechSynthesis.getVoices());
      if (voice) utterance.voice = voice;
      utterance.onstart = () => {
        this.startedAt = performance.now();
        onFirstAudio?.(this.startedAt - requested);
      };
      const finish = (outcome: "completed" | "aborted") => {
        this.active = false;
        resolve(outcome);
      };
      utterance.onend = () => finish("completed");
      utterance.onerror = () => finish("aborted");
      this.active = true;
      speechSynthesis.speak(utterance);
    });
  }

  stop(): void {
    if (!browserCanSpeak()) return;
    this.active = false;
    speechSynthesis.cancel();
  }
}

export interface ListenerCallbacks {
  /** A finished sentence from the owner. `endedAt` is performance.now() at the end of speech. */
  onTranscript: (text: string, endedAt: number) => void;
  onSpeechStart: () => void;
  onError: (message: string) => void;
}

/**
 * Continuous recognition for one call. Browsers stop recognising after a silence, so it restarts
 * itself until the call ends. While the agent talks it pauses: device recognition has no echo
 * cancellation and would hear the agent as the owner.
 */
export class BrowserListener {
  private recognition: Recognition | null = null;
  private running = false;
  private paused = false;

  constructor(private readonly callbacks: ListenerCallbacks) {}

  get active(): boolean {
    return this.running;
  }

  start(): void {
    const Klass = recognitionClass();
    if (!Klass) throw new Error("este navegador não reconhece fala");
    this.running = true;
    this.paused = false;
    this.recognition = new Klass();
    this.recognition.lang = "pt-BR";
    this.recognition.continuous = true;
    this.recognition.interimResults = false;
    this.recognition.onspeechstart = () => this.callbacks.onSpeechStart();
    this.recognition.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const text = result[0]?.transcript.trim() ?? "";
        if (result.isFinal && text) this.callbacks.onTranscript(text, performance.now());
      }
    };
    this.recognition.onerror = (event) => {
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        this.running = false;
        this.callbacks.onError("o microfone foi negado");
      }
    };
    this.recognition.onend = () => {
      if (this.running && !this.paused) this.safeStart();
    };
    this.safeStart();
  }

  /** Stops hearing while the agent talks; `resume` picks up again. */
  pause(): void {
    if (!this.running || this.paused) return;
    this.paused = true;
    this.recognition?.abort();
  }

  resume(): void {
    if (!this.running || !this.paused) return;
    this.paused = false;
    this.safeStart();
  }

  stop(): void {
    this.running = false;
    this.recognition?.abort();
    this.recognition = null;
  }

  level(): number {
    return 0;
  }

  private safeStart(): void {
    try {
      this.recognition?.start();
    } catch {
      // Already started: the browser throws instead of ignoring a second start.
    }
  }
}
