// Microphone capture for one voice session. Opened only by an explicit user action and closed
// when the session ends or the page is hidden: there is no background listening.

import { VoiceActivityDetector, rms } from "./vad";
import { STT_SAMPLE_RATE, concat, downsample, encodeWav } from "./wav";

const FRAME_MS = 20;
const PRE_ROLL_MS = 300;
const MAX_UTTERANCE_MS = 30_000;

// Runs on the audio thread; forwards raw mono samples to the page.
const WORKLET_SOURCE = `
class CaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("visao-capture", CaptureProcessor);
`;

export interface Utterance {
  wav: Blob;
  durationMs: number;
  /** performance.now() when the end of speech was detected: start of the latency clock. */
  endedAt: number;
}

export interface MicrophoneCallbacks {
  onSpeechStart: () => void;
  onUtterance: (utterance: Utterance) => void;
  /** Whether the agent is talking right now (raises the detection threshold). */
  agentSpeaking: () => boolean;
}

export class Microphone {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private readonly vad = new VoiceActivityDetector();
  private pending: Float32Array[] = [];
  private pendingLength = 0;
  private preRoll: Float32Array[] = [];
  private segment: Float32Array[] | null = null;
  private segmentStartedAt = 0;
  private lastLevel = 0;

  constructor(private readonly callbacks: MicrophoneCallbacks) {}

  get active(): boolean {
    return this.stream !== null;
  }

  /** Must be called from a user gesture; the browser asks for permission the first time. */
  async start(): Promise<void> {
    if (this.stream) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.context = new AudioContext();
    const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "text/javascript" }));
    try {
      await this.context.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    const source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "visao-capture");
    this.node.port.onmessage = (event: MessageEvent<Float32Array>) => this.onSamples(event.data);
    source.connect(this.node);
    // Not connected to the speakers: the microphone is never played back.
  }

  stop(): void {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close();
    this.node = null;
    this.stream = null;
    this.context = null;
    this.vad.reset();
    this.pending = [];
    this.pendingLength = 0;
    this.preRoll = [];
    this.segment = null;
    this.lastLevel = 0;
  }

  /** Current input level 0..1 for the orb. */
  level(): number {
    return Math.min(1, this.lastLevel * 6);
  }

  private onSamples(samples: Float32Array): void {
    if (!this.context) return;
    const frameSize = Math.round((this.context.sampleRate * FRAME_MS) / 1000);
    this.pending.push(samples);
    this.pendingLength += samples.length;
    while (this.pendingLength >= frameSize) {
      const all = concat(this.pending);
      this.onFrame(all.subarray(0, frameSize).slice());
      const rest = all.subarray(frameSize).slice();
      this.pending = rest.length ? [rest] : [];
      this.pendingLength = rest.length;
    }
  }

  private onFrame(frame: Float32Array): void {
    const now = performance.now();
    const level = rms(frame);
    this.lastLevel = level;
    const event = this.vad.process(level, now, this.callbacks.agentSpeaking());

    if (this.segment) this.segment.push(frame);
    else {
      this.preRoll.push(frame);
      while (this.preRoll.length * FRAME_MS > PRE_ROLL_MS) this.preRoll.shift();
    }

    if (event === "start") {
      // Keep the audio from just before detection so the first syllable is not cut.
      this.segment = [...this.preRoll];
      this.preRoll = [];
      this.segmentStartedAt = now - this.segment.length * FRAME_MS;
      this.callbacks.onSpeechStart();
    } else if (
      this.segment &&
      (event === "end" || now - this.segmentStartedAt > MAX_UTTERANCE_MS)
    ) {
      if (event !== "end") this.vad.reset();
      this.finishSegment(now);
    }
  }

  private finishSegment(endedAt: number): void {
    const samples = concat(this.segment ?? []);
    this.segment = null;
    if (!this.context || samples.length === 0) return;
    const resampled = downsample(samples, this.context.sampleRate, STT_SAMPLE_RATE);
    this.callbacks.onUtterance({
      wav: new Blob([encodeWav(resampled, STT_SAMPLE_RATE)], { type: "audio/wav" }),
      durationMs: (samples.length / this.context.sampleRate) * 1000,
      endedAt,
    });
  }
}
