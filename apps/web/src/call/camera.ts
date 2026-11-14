import { useCallback, useEffect, useRef, useState } from "react";

/** The long side of a picture sent from the call, as the photos the chat sends (1568 px). */
export const MAX_SIDE = 1568;

/** The size that fits `max` on the long side, never enlarging. */
export function fitWithin(width: number, height: number, max = MAX_SIDE): { width: number; height: number } {
  const long = Math.max(width, height);
  if (long <= max || long === 0) return { width, height };
  const scale = max / long;
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

export type Facing = "environment" | "user";

/** Whether this browser can open a camera at all (https or localhost, and a camera API). */
export function cameraSupported(): boolean {
  return typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
}

/**
 * The camera in a call (as on the iPhone): while it is on, what it shows goes with each sentence
 * you say, so you can point it and ask "o que é isso?". Video only, on only by its button, and off
 * when the call ends.
 */
export function useCallCamera(active: boolean) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [facing, setFacing] = useState<Facing>("environment");
  const [error, setError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStream(null);
  }, []);

  const open = useCallback(
    async (side: Facing) => {
      setError(null);
      try {
        const next = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: side } }, audio: false });
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = next;
        setStream(next);
        setFacing(side);
      } catch (e) {
        const denied = e instanceof DOMException && (e.name === "NotAllowedError" || e.name === "SecurityError");
        setError(denied ? "Para ele ver pela câmera, permita a câmera para este site no navegador." : "A câmera não está disponível agora.");
      }
    },
    [],
  );

  const toggle = useCallback(() => {
    if (streamRef.current) stop();
    else void open(facing);
  }, [facing, open, stop]);

  const flip = useCallback(() => {
    void open(facing === "environment" ? "user" : "environment");
  }, [facing, open]);

  // Hanging up turns it off; nothing keeps watching outside a call.
  useEffect(() => {
    if (!active) stop();
  }, [active, stop]);
  useEffect(() => stop, [stop]);

  /** What the camera shows right now, as a JPEG; null when it is off or has no picture yet. */
  const snapshot = useCallback(async (): Promise<Blob | null> => {
    const video = videoRef.current;
    if (!streamRef.current || !video || !video.videoWidth) return null;
    const size = fitWithin(video.videoWidth, video.videoHeight);
    const canvas = document.createElement("canvas");
    canvas.width = size.width;
    canvas.height = size.height;
    const context = canvas.getContext("2d");
    if (!context) return null;
    if (facing === "user") {
      // The preview is mirrored for the front camera; the picture is the same way round.
      context.translate(size.width, 0);
      context.scale(-1, 1);
    }
    context.drawImage(video, 0, 0, size.width, size.height);
    return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.85));
  }, [facing]);

  return { stream, on: stream !== null, facing, error, videoRef, toggle, flip, snapshot };
}

export type CallCamera = ReturnType<typeof useCallCamera>;
