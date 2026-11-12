// Web Push in the browser: opt-in, one subscription per device. On iPhone it only works from
// the app installed on the home screen (Safari's rule, iOS 16.4+).

import type { Api } from "./api";

export type PushSupport = "supported" | "needs-install" | "unsupported";

export function pushSupport(): PushSupport {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    const ios = /iPhone|iPad|iPod/.test(navigator.userAgent);
    const standalone = window.matchMedia?.("(display-mode: standalone)").matches;
    return ios && !standalone ? "needs-install" : "unsupported";
  }
  return "supported";
}

/** Base64url (VAPID public key) to the bytes PushManager expects. */
export function keyBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  const raw = atob(padded);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export async function registerWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker?.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

/** Must run inside a click: browsers only ask for notification permission from a gesture. */
export async function subscribe(api: Api, publicKey: string): Promise<void> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("os avisos foram negados neste aparelho");
  const registration = (await registerWorker()) ?? (await navigator.serviceWorker.ready);
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: keyBytes(publicKey) as BufferSource,
  });
  const json = subscription.toJSON();
  await api.subscribePush({
    endpoint: subscription.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
  });
}

export async function unsubscribe(api: Api): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api.unsubscribePush(subscription.endpoint).catch(() => undefined);
  await subscription.unsubscribe();
}
