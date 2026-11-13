// Web Push in the browser: opt-in, one subscription per device. On iPhone it only works from
// the app installed on the home screen (Safari's rule, iOS 16.4+).

import type { Api } from "./api";
import { loadPreference, savePreference } from "./session";

/** "off" once the owner turned avisos off on this device: sync never turns them back on. */
const PREFERENCE = "push";

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

/** Whether a subscription was made for this server key. A subscription made for another key
 * (the server's VAPID keys changed, as in the move to a new server) is refused by the push
 * service, so it has to be replaced. Browsers that do not expose the key are trusted. */
export function sameKey(subscription: PushSubscription, publicKey: string): boolean {
  const current = subscription.options?.applicationServerKey;
  if (!current) return true;
  const a = new Uint8Array(current);
  const b = keyBytes(publicKey);
  return a.length === b.length && a.every((byte, i) => byte === b[i]);
}

async function readyRegistration(): Promise<ServiceWorkerRegistration> {
  return (await registerWorker()) ?? (await navigator.serviceWorker.ready);
}

async function send(api: Api, subscription: PushSubscription): Promise<void> {
  const json = subscription.toJSON();
  await api.subscribePush({
    endpoint: subscription.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
  });
}

/** This device's subscription for `publicKey`: the current one, or a new one in its place. */
async function freshSubscription(publicKey: string): Promise<PushSubscription> {
  const registration = await readyRegistration();
  let subscription = await registration.pushManager.getSubscription();
  if (subscription && !sameKey(subscription, publicKey)) {
    await subscription.unsubscribe().catch(() => undefined);
    subscription = null;
  }
  return (
    subscription ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey) as BufferSource,
    }))
  );
}

/** Must run inside a click: browsers only ask for notification permission from a gesture. */
export async function subscribe(api: Api, publicKey: string): Promise<void> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("os avisos foram negados neste aparelho");
  await send(api, await freshSubscription(publicKey));
  savePreference(PREFERENCE, "on");
}

export async function unsubscribe(api: Api): Promise<void> {
  savePreference(PREFERENCE, "off");
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api.unsubscribePush(subscription.endpoint).catch(() => undefined);
  await subscription.unsubscribe();
}

/**
 * Runs every time the app opens. The switch used to be the only moment a device registered, so
 * a subscription the server dropped (after failures), one the phone renewed, or one made for old
 * VAPID keys left the switch on and the avisos silently gone. Here the device re-sends what it
 * has (the server upserts) and replaces a subscription made for another key. It never asks for
 * permission and never undoes the owner turning avisos off on this device.
 */
export async function syncSubscription(api: Api): Promise<boolean> {
  if (pushSupport() !== "supported" || Notification.permission !== "granted") return false;
  if (loadPreference(PREFERENCE) === "off") return false;
  const state = await api.pushState();
  if (!state.enabled || !state.public_key) return false;
  await send(api, await freshSubscription(state.public_key));
  return true;
}
