// One voice for the app, whichever engine is behind it. The server's own models (the agent's
// chosen voice, self-hosted STT) come first; the device's engines cover the cloud build, where
// there are none, so a call works from the phone. Device recognition needs the owner's consent.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Api, VoiceStatus } from "../api";
import { Speaker } from "../speech/speaker";
import { BrowserListener, BrowserSpeaker, browserCanListen, browserCanSpeak } from "../voice/browser";
import { Microphone, type Utterance } from "../voice/microphone";

export type Engine = "server" | "device";

export interface SpokenTiming {
  /** performance.now() at the end of the owner's speech. */
  endedAt: number;
  sttMs: number;
}

interface Options {
  api: Api;
  status: VoiceStatus | null;
  /** The owner allowed device recognition (it may send audio to the browser maker). */
  deviceListening: boolean;
  onTranscript: (text: string, timing: SpokenTiming) => Promise<void>;
  onError: (message: string) => void;
}

interface Listener {
  stop(): void;
  level(): number;
  pause?(): void;
  resume?(): void;
}

export function useVoice({ api, status, deviceListening, onTranscript, onError }: Options) {
  const serverSpeaker = useMemo(() => new Speaker(api), [api]);
  const deviceSpeaker = useMemo(() => new BrowserSpeaker(), []);
  const speakerKind: Engine | null = status?.enabled ? "server" : browserCanSpeak() ? "device" : null;
  const listenerKind: Engine | null = status?.enabled && status.listening
    ? "server"
    : deviceListening && browserCanListen()
      ? "device"
      : null;
  const deviceCouldListen = browserCanListen();
  const speaker = speakerKind === "server" ? serverSpeaker : deviceSpeaker;

  const [speaking, setSpeaking] = useState(false);
  const [interrupted, setInterrupted] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [inCall, setInCall] = useState(false);
  const listenerRef = useRef<Listener | null>(null);
  const busyRef = useRef(false);
  const wakeRef = useRef<{ release(): Promise<void> } | null>(null);
  const transcriptRef = useRef(onTranscript);
  const errorRef = useRef(onError);
  transcriptRef.current = onTranscript;
  errorRef.current = onError;

  const unlock = useCallback(() => speaker.unlock(), [speaker]);

  const stopSpeaking = useCallback(() => {
    if (!speaker.speaking) return;
    speaker.stop();
    setSpeaking(false);
    setInterrupted(true);
    setTimeout(() => setInterrupted(false), 700);
    listenerRef.current?.resume?.();
  }, [speaker]);

  const speak = useCallback(
    (text: string, onFirstAudio?: (ms: number) => void) => {
      if (!speakerKind) return;
      setSpeaking(true);
      // Device recognition has no echo cancellation: it would hear the agent as the owner.
      listenerRef.current?.pause?.();
      speaker
        .speak(text, onFirstAudio)
        .catch((e) => errorRef.current(`Voz indisponível (${e instanceof Error ? e.message : e}); sigo por texto.`))
        .finally(() => {
          setSpeaking(false);
          listenerRef.current?.resume?.();
        });
    },
    [speaker, speakerKind],
  );

  const handle = useCallback(async (text: string, timing: SpokenTiming) => {
    // One turn at a time: speech that arrives while a turn is in flight is dropped.
    if (busyRef.current || text.trim().length < 2) return;
    busyRef.current = true;
    try {
      await transcriptRef.current(text.trim(), timing);
    } finally {
      busyRef.current = false;
    }
  }, []);

  const endCall = useCallback(() => {
    listenerRef.current?.stop();
    listenerRef.current = null;
    setInCall(false);
    void wakeRef.current?.release().catch(() => undefined);
    wakeRef.current = null;
  }, []);

  const startCall = useCallback(async () => {
    if (!listenerKind) return;
    speaker.unlock(); // inside the click: lets replies play
    try {
      if (listenerKind === "server") {
        const microphone = new Microphone({
          agentSpeaking: () => speaker.speaking,
          onSpeechStart: () => stopSpeaking(), // barge-in by voice
          onUtterance: (u: Utterance) => {
            if (busyRef.current) return;
            setTranscribing(true);
            api
              .stt(u.wav)
              .then((t) => {
                setTranscribing(false);
                return handle(t.text, { endedAt: u.endedAt, sttMs: performance.now() - u.endedAt });
              })
              .catch((e) => errorRef.current(e instanceof Error ? e.message : String(e)))
              .finally(() => setTranscribing(false));
          },
        });
        await microphone.start();
        listenerRef.current = microphone;
      } else {
        const listener = new BrowserListener({
          onSpeechStart: () => undefined,
          onTranscript: (text, endedAt) => void handle(text, { endedAt, sttMs: 0 }),
          onError: (message) => {
            errorRef.current(`Microfone indisponível: ${message}. A conversa continua por texto.`);
            endCall();
          },
        });
        listener.start();
        listenerRef.current = listener;
      }
      setInCall(true);
      // Keep the screen on during a call, where the browser allows it.
      const lock = (navigator as Navigator & { wakeLock?: { request(type: "screen"): Promise<{ release(): Promise<void> }> } }).wakeLock;
      lock?.request("screen").then((w) => { wakeRef.current = w; }).catch(() => undefined);
    } catch (e) {
      listenerRef.current?.stop();
      listenerRef.current = null;
      errorRef.current(`Microfone indisponível (${e instanceof Error ? e.message : e}). A conversa continua por texto.`);
    }
  }, [api, endCall, handle, listenerKind, speaker, stopSpeaking]);

  // No listening in the background: hiding the page ends the call.
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") endCall();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      listenerRef.current?.stop();
    };
  }, [endCall]);

  const level = useCallback(
    () => (speaking ? speaker.level() : listenerRef.current?.level() ?? 0),
    [speaker, speaking],
  );

  return {
    speakerKind,
    listenerKind,
    deviceCouldListen,
    speaking,
    interrupted,
    transcribing,
    inCall,
    speak,
    stopSpeaking,
    unlock,
    startCall,
    endCall,
    level,
  };
}

export type Voice = ReturnType<typeof useVoice>;
