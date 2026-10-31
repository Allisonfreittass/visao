// Browser playback of synthesized speech: Web Audio, with a live level for the orb.

import type { Api } from "../api";
import { speakSentences } from "./queue";

export class Speaker {
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private controller: AbortController | null = null;
  private source: AudioBufferSourceNode | null = null;
  private readonly samples = new Float32Array(1024);

  constructor(private readonly api: Api) {}

  get speaking(): boolean {
    return this.controller !== null;
  }

  /** Must be called from a user gesture at least once (browser autoplay policy). */
  unlock(): void {
    if (!this.context) {
      this.context = new AudioContext();
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.connect(this.context.destination);
    }
    void this.context.resume();
  }

  /** RMS of what is playing right now, scaled to 0..1. Cheap; called every animation frame. */
  level(): number {
    if (!this.analyser || !this.source) return 0;
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const v of this.samples) sum += v * v;
    return Math.min(1, Math.sqrt(sum / this.samples.length) * 4);
  }

  async speak(text: string, onFirstAudio?: (ms: number) => void): Promise<"completed" | "aborted"> {
    this.stop();
    this.unlock();
    const controller = new AbortController();
    this.controller = controller;
    try {
      const sentences = await this.api.sentences(text);
      return await speakSentences(sentences, {
        signal: controller.signal,
        onFirstAudio,
        synthesize: async (sentence, signal) => {
          const bytes = await this.api.tts(sentence, signal);
          return this.context!.decodeAudioData(bytes);
        },
        play: (buffer, signal) => this.play(buffer, signal),
      });
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }

  /** Barge-in: cut current audio and drop everything queued. */
  stop(): void {
    this.controller?.abort();
    this.controller = null;
    try {
      this.source?.stop();
    } catch {
      // Already stopped.
    }
    this.source = null;
  }

  private play(buffer: AudioBuffer, signal: AbortSignal): Promise<void> {
    return new Promise((resolve) => {
      const source = this.context!.createBufferSource();
      source.buffer = buffer;
      source.connect(this.analyser!);
      this.source = source;
      const done = () => {
        if (this.source === source) this.source = null;
        resolve();
      };
      source.onended = done;
      signal.addEventListener("abort", done, { once: true });
      source.start();
    });
  }
}
