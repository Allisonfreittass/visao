// Plays sentences in order while synthesizing the next one in the background, so the listener
// waits only for the first sentence. Pure orchestration: synthesis and playback are injected.

export interface SpeakOptions<T> {
  synthesize: (sentence: string, signal: AbortSignal) => Promise<T>;
  play: (clip: T, signal: AbortSignal) => Promise<void>;
  signal: AbortSignal;
  onFirstAudio?: (msSinceStart: number) => void;
}

export type SpeakOutcome = "completed" | "aborted";

export async function speakSentences<T>(
  sentences: string[],
  { synthesize, play, signal, onFirstAudio }: SpeakOptions<T>,
): Promise<SpeakOutcome> {
  const started = performance.now();
  let next: Promise<T> | null = sentences.length ? synthesize(sentences[0], signal) : null;
  for (let i = 0; i < sentences.length; i++) {
    if (signal.aborted) return "aborted";
    let clip: T;
    try {
      clip = await next!;
    } catch (error) {
      if (signal.aborted) return "aborted";
      throw error;
    }
    // Prefetch the following sentence before playing this one.
    next = i + 1 < sentences.length ? synthesize(sentences[i + 1], signal) : null;
    next?.catch(() => undefined); // surfaced when awaited; avoids unhandled-rejection noise
    if (i === 0) onFirstAudio?.(performance.now() - started);
    if (signal.aborted) return "aborted";
    await play(clip, signal);
  }
  return signal.aborted ? "aborted" : "completed";
}
