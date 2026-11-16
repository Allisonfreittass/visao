// The phone's position for "is there a pharmacy open near here?" (docs/LOCALIZACAO.md, ADR-0020).
// Off by default, per device. When on, it leaves the phone only with a message that looks like a
// question about somewhere nearby; the server checks again and never stores it.

const KEY = "visao.location";

export interface Position {
  lat: number;
  lon: number;
  accuracy_m: number | null;
  at: string;
}

export function locationOn(): boolean {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

export function setLocationOn(on: boolean): void {
  try {
    if (on) localStorage.setItem(KEY, "on");
    else localStorage.removeItem(KEY);
  } catch {
    // private window: it just stays off
  }
}

function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

// Same idea as core/location.py: "perto do Natal" and "daqui a pouco" are not about a place.
const NEARBY =
  /\bperto (daqui|de mim|de onde (eu )?(estou|to))\b|\bperto\s*[?!.]*\s*$|\bmais perto\b|\baqui perto\b|\bpertinho\b|\bpor aqui\b|\baqui (do lado|na rua|no bairro|na regiao)\b|\bmais proxim[oa]s? (daqui|de mim)\b|\b(na|nessa|nesta) (minha )?regiao\b|\bao (meu )?redor\b|\bnos arredores\b|\bonde (eu )?(estou|to) agora\b/;

export function asksNearby(text: string): boolean {
  return text.length <= 1000 && NEARBY.test(fold(text));
}

/** The current position, or null (no permission, no signal, too slow). */
export function currentPosition(timeoutMs = 4000): Promise<Position | null> {
  if (typeof navigator === "undefined" || !navigator.geolocation) return Promise.resolve(null);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (p) =>
        resolve({
          lat: p.coords.latitude,
          lon: p.coords.longitude,
          accuracy_m: Number.isFinite(p.coords.accuracy) ? p.coords.accuracy : null,
          at: new Date(p.timestamp).toISOString(),
        }),
      () => resolve(null),
      { enableHighAccuracy: false, maximumAge: 120_000, timeout: timeoutMs },
    );
  });
}

/** The position to send with this message, only when it is on and the message asks for it. */
export async function positionFor(text: string): Promise<Position | null> {
  if (!locationOn() || !asksNearby(text)) return null;
  return currentPosition();
}
