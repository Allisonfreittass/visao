import { describe, expect, it } from "vitest";

import { DEFAULT_VAD, VoiceActivityDetector, rms } from "./vad";
import { concat, downsample, encodeWav } from "./wav";

const FRAME_MS = 20;

/** Feeds a constant RMS for a duration; returns events with their timestamps. */
function feed(vad: VoiceActivityDetector, level: number, ms: number, start: number, speaking = false) {
  const events: Array<[string, number]> = [];
  for (let t = start; t < start + ms; t += FRAME_MS) {
    const event = vad.process(level, t, speaking);
    if (event) events.push([event, t]);
  }
  return { events, end: start + ms };
}

describe("voice activity detection", () => {
  it("starts after sustained speech and ends after the hangover", () => {
    const vad = new VoiceActivityDetector();
    let t = feed(vad, 0.002, 1000, 0).end; // quiet room
    const speech = feed(vad, 0.1, 1000, t);
    t = speech.end;
    const silence = feed(vad, 0.002, 1500, t);

    // Decisions land on the first frame at or after the configured duration.
    const onFrame = (ms: number) => Math.ceil(ms / FRAME_MS) * FRAME_MS;
    expect(speech.events).toEqual([["start", 1000 + onFrame(DEFAULT_VAD.minSpeechMs)]]);
    expect(silence.events).toEqual([["end", t + onFrame(DEFAULT_VAD.hangoverMs)]]);
  });

  it("ignores short clicks and pops", () => {
    const vad = new VoiceActivityDetector();
    const t = feed(vad, 0.002, 1000, 0).end;
    expect(feed(vad, 0.3, 100, t).events).toEqual([]);
  });

  it("adapts to a noisy room instead of firing forever", () => {
    const vad = new VoiceActivityDetector();
    // Steady fan noise slightly above the absolute minimum threshold.
    feed(vad, 0.01, 5000, 0);
    expect(vad.threshold(false)).toBeGreaterThan(0.025);
    expect(feed(vad, 0.011, 2000, 5000).events).toEqual([]);
  });

  it("needs a louder voice to interrupt while the agent speaks", () => {
    const vad = new VoiceActivityDetector();
    const t = feed(vad, 0.002, 1000, 0).end;
    // Echo of the agent's own voice at moderate level: not an interruption.
    expect(feed(vad, 0.02, 1000, t, true).events).toEqual([]);
    // The user speaking clearly over it: interruption.
    expect(feed(vad, 0.2, 400, t + 1000, true).events[0]?.[0]).toBe("start");
  });

  it("computes RMS", () => {
    expect(rms(new Float32Array([0.5, -0.5, 0.5, -0.5]))).toBeCloseTo(0.5);
    expect(rms(new Float32Array(0))).toBe(0);
  });
});

describe("wav helpers", () => {
  it("downsamples 48 kHz to 16 kHz by averaging", () => {
    const input = new Float32Array([0, 0.3, 0.6, 1, 1, 1]);
    expect(Array.from(downsample(input, 48_000, 16_000))).toEqual([
      expect.closeTo(0.3, 6),
      expect.closeTo(1, 6),
    ]);
  });

  it("encodes a valid mono 16-bit WAV header and clamps samples", () => {
    const wav = new DataView(encodeWav(new Float32Array([0, 1, -1, 2]), 16_000));
    const text = (o: number) =>
      String.fromCharCode(...[0, 1, 2, 3].map((i) => wav.getUint8(o + i)));
    expect(text(0)).toBe("RIFF");
    expect(text(8)).toBe("WAVE");
    expect(wav.getUint32(24, true)).toBe(16_000);
    expect(wav.getUint32(40, true)).toBe(8);
    expect(wav.getInt16(46, true)).toBe(0x7fff);
    expect(wav.getInt16(48, true)).toBe(-0x8000);
    expect(wav.getInt16(50, true)).toBe(0x7fff); // 2 clamped to 1
  });

  it("concatenates frames", () => {
    const out = concat([new Float32Array([1, 2]), new Float32Array([3])]);
    expect(Array.from(out)).toEqual([1, 2, 3]);
  });
});
