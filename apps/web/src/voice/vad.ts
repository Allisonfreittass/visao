// Energy-based voice activity detection with an adaptive noise floor. Pure and deterministic:
// frames of RMS go in, "start"/"end" events come out. Timing is in milliseconds.

export interface VadOptions {
  /** Speech must stay above threshold this long before a turn starts. */
  minSpeechMs: number;
  /** Silence this long ends the turn. */
  hangoverMs: number;
  /** Absolute floor for the threshold (quiet rooms). */
  minThreshold: number;
  /** Threshold = max(minThreshold, noiseFloor * ratio). */
  ratio: number;
  /** Extra factor while the agent is speaking, so its own voice leaking into the mic does
   * not count as the user interrupting (acoustic echo is only partly cancelled by browsers). */
  speakingFactor: number;
}

export const DEFAULT_VAD: VadOptions = {
  minSpeechMs: 250,
  hangoverMs: 800,
  minThreshold: 0.012,
  ratio: 3,
  speakingFactor: 2.5,
};

export type VadEvent = "start" | "end" | null;

export class VoiceActivityDetector {
  private noiseFloor = 0;
  private aboveSince: number | null = null;
  private belowSince: number | null = null;
  private inSpeech = false;

  constructor(private readonly options: VadOptions = DEFAULT_VAD) {}

  get speaking(): boolean {
    return this.inSpeech;
  }

  threshold(agentSpeaking: boolean): number {
    const base = Math.max(this.options.minThreshold, this.noiseFloor * this.options.ratio);
    return agentSpeaking ? base * this.options.speakingFactor : base;
  }

  process(rms: number, nowMs: number, agentSpeaking = false): VadEvent {
    const loud = rms > this.threshold(agentSpeaking);

    if (!this.inSpeech) {
      // Learn the room only while nobody is talking: slow rise, fast fall.
      if (!loud) {
        const rate = rms > this.noiseFloor ? 0.02 : 0.2;
        this.noiseFloor += (rms - this.noiseFloor) * rate;
      }
      if (loud) {
        this.aboveSince ??= nowMs;
        if (nowMs - this.aboveSince >= this.options.minSpeechMs) {
          this.inSpeech = true;
          this.belowSince = null;
          return "start";
        }
      } else {
        this.aboveSince = null;
      }
      return null;
    }

    if (loud) {
      this.belowSince = null;
      return null;
    }
    this.belowSince ??= nowMs;
    if (nowMs - this.belowSince >= this.options.hangoverMs) {
      this.inSpeech = false;
      this.aboveSince = null;
      return "end";
    }
    return null;
  }

  reset(): void {
    this.inSpeech = false;
    this.aboveSince = null;
    this.belowSince = null;
  }
}

export function rms(samples: Float32Array): number {
  let sum = 0;
  for (const v of samples) sum += v * v;
  return Math.sqrt(sum / Math.max(samples.length, 1));
}
