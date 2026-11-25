// The call's nanorrobôs (DESIGN.md §6): while he uses a tool, Muninn's particles take its shape,
// and they go back to being the crow when it ends. Pure, so it can be tested; the canvas is
// Nanorrobos.tsx. Everything here is in the ring's own space, 0..1000 with the centre at 500.

/** The crow, or the shape of a tool. The tools are the server's step kinds
 * (core/conversation/progress.py KINDS). */
export type Forma = "corvo" | "gmail" | "agenda" | "pesquisa" | "site" | "mac" | "arquivo";
export type Ferramenta = Exclude<Forma, "corvo">;

export const FERRAMENTAS: readonly Ferramenta[] = ["gmail", "agenda", "pesquisa", "site", "mac", "arquivo"];

/** Each shape stays at least this long once it is formed; quick steps in between are skipped. */
export const HOLD_MS = 1200;
/** Each particle's flight, and the most it waits before taking off. */
export const MORPH_S = 1.6;
export const MAX_DELAY_S = 0.5;
/** From the moment a shape is chosen until every particle is in it. */
export const MORPH_MS = (MORPH_S + MAX_DELAY_S) * 1000;
/** With reduced motion there is no flight: the crow and the icon cross-fade. */
export const FADE_MS = 200;
/** The sideways curve of a flight, as a share of its length. */
export const BEND = 0.22;
/** The share of particles that are amber, the same ones in every shape. */
export const AMBER_SHARE = 0.025;
/** At rest every particle trembles this much, in CSS px. */
export const TREMOR_PX = 0.6;
export const CENTER = 500;

/** "Pensando" and "Escrevendo a resposta" are him, not a tool: back to the crow. */
const CROW_STEPS = new Set(["Pensando", "Escrevendo a resposta"]);

export interface Passo {
  label: string;
  kind?: string | null;
}

export const isFerramenta = (kind: unknown): kind is Ferramenta => typeof kind === "string" && (FERRAMENTAS as readonly string[]).includes(kind);

/** The shape a step asks for. Only a real kind changes it; the end of the turn (no step),
 * "Pensando" and "Escrevendo a resposta" go back to the crow; any other step keeps `atual`. */
export function formaDoPasso(passo: Passo | null, atual: Forma): Forma {
  if (passo === null) return "corvo";
  if (isFerramenta(passo.kind)) return passo.kind;
  if (CROW_STEPS.has(passo.label)) return "corvo";
  return atual;
}

/** 3000 particles; 2000 on a screen under 400 px wide. */
export const particleCount = (screenWidth: number) => (screenWidth < 400 ? 2000 : 3000);

/** Which shape shows, when it is complete, and the one waiting for its turn. */
export interface Agenda {
  forma: Forma;
  /** When every particle is in `forma` (ms, the caller's clock). */
  pronta: number;
  pendente: Forma | null;
}

/** A call opens with the crow, already formed. */
export const agendaInicial = (): Agenda => ({ forma: "corvo", pronta: -Infinity, pendente: null });

/** The owner's turn wants `desejada` now. It shows at once when the current shape has been formed
 * for HOLD_MS; else it waits, replacing whatever was waiting (quick steps go straight to the last).
 * `morphMs`: how long the change takes (MORPH_MS, or FADE_MS with reduced motion). */
export function pedir(agenda: Agenda, desejada: Forma, agora: number, morphMs: number = MORPH_MS): Agenda {
  if (desejada === agenda.forma) return agenda.pendente === null ? agenda : { ...agenda, pendente: null };
  if (agora >= agenda.pronta + HOLD_MS) return { forma: desejada, pronta: agora + morphMs, pendente: null };
  return agenda.pendente === desejada ? agenda : { ...agenda, pendente: desejada };
}

/** When the waiting shape may show (ms), or null with nothing waiting. */
export const proximaTroca = (agenda: Agenda): number | null => (agenda.pendente === null ? null : agenda.pronta + HOLD_MS);

// ---- Drawing -------------------------------------------------------------------------------

const rect = (x0: number, y0: number, x1: number, y1: number) => [x0, y0, x1, y0, x1, y1, x0, y1, x0, y0];
const circle = (cx: number, cy: number, r: number, segs = 48) => {
  const pts: number[] = [];
  for (let i = 0; i <= segs; i++) {
    const a = (i / segs) * Math.PI * 2;
    pts.push(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  }
  return pts;
};

/** The six tools as simple line drawings (flat [x, y, x, y…] polylines), centred in the ring. */
export const DESENHOS: Record<Ferramenta, number[][]> = {
  // An envelope: the body and its flap.
  gmail: [rect(290, 360, 710, 640), [290, 360, 500, 525, 710, 360]],
  // A calendar: the page, the header, the two rings and the grid of days.
  agenda: [
    rect(300, 330, 700, 690),
    [300, 420, 700, 420],
    [400, 290, 400, 370],
    [600, 290, 600, 370],
    [300, 510, 700, 510],
    [300, 600, 700, 600],
    [433, 420, 433, 690],
    [567, 420, 567, 690],
  ],
  // A magnifying glass.
  pesquisa: [circle(465, 465, 155), [575, 575, 700, 700]],
  // A browser window: the frame, the bar with three dots, and lines of a page.
  site: [
    rect(270, 320, 730, 680),
    [270, 395, 730, 395],
    circle(315, 357, 11, 12),
    circle(352, 357, 11, 12),
    circle(389, 357, 11, 12),
    rect(430, 342, 700, 372),
    [320, 465, 680, 465],
    [320, 530, 620, 530],
    [320, 595, 560, 595],
  ],
  // A notebook: the screen and the base.
  mac: [rect(320, 320, 680, 585), rect(350, 350, 650, 555), [320, 585, 255, 650, 745, 650, 680, 585]],
  // A page with its corner folded and lines of text.
  arquivo: [
    [340, 280, 600, 280, 660, 340, 660, 720, 340, 720, 340, 280],
    [600, 280, 600, 340, 660, 340],
    [395, 420, 605, 420],
    [395, 480, 605, 480],
    [395, 540, 605, 540],
    [395, 600, 540, 600],
  ],
};

/** The drawing as an SVG path, in the same space (the icon of reduced motion). */
export function pathOf(linhas: number[][]): string {
  return linhas
    .map((pts) => {
      let d = `M${pts[0]} ${pts[1]}`;
      for (let k = 2; k < pts.length; k += 2) d += `L${pts[k]} ${pts[k + 1]}`;
      return d;
    })
    .join("");
}

/** A small seeded random, so every call draws the same shapes. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Sorts [x, y] pairs by their angle round the centre, so particle i of one shape flies to point i
 * of the next: each moves round the ring as little as it can. */
export function porAngulo(pts: Float32Array): Float32Array {
  const n = pts.length / 2;
  const angle = new Float64Array(n);
  for (let i = 0; i < n; i++) angle[i] = Math.atan2(pts[i * 2 + 1] - CENTER, pts[i * 2] - CENTER);
  const order = Array.from({ length: n }, (_, i) => i).sort((a, b) => angle[a] - angle[b]);
  const out = new Float32Array(n * 2);
  order.forEach((from, to) => {
    out[to * 2] = pts[from * 2];
    out[to * 2 + 1] = pts[from * 2 + 1];
  });
  return out;
}

/** `n` points spread evenly along the lines, a little off them (`spread`, either side) so the line
 * reads as particles; sorted by angle. */
export function amostrar(linhas: number[][], n: number, rand: () => number, spread = 4): Float32Array {
  const segs: { x: number; y: number; dx: number; dy: number; len: number }[] = [];
  let total = 0;
  for (const pts of linhas) {
    for (let k = 2; k < pts.length; k += 2) {
      const dx = pts[k] - pts[k - 2];
      const dy = pts[k + 1] - pts[k - 1];
      const len = Math.hypot(dx, dy);
      if (len > 0) {
        segs.push({ x: pts[k - 2], y: pts[k - 1], dx, dy, len });
        total += len;
      }
    }
  }
  const out = new Float32Array(n * 2);
  if (!segs.length) {
    out.fill(CENTER);
    return out;
  }
  let seg = 0;
  let before = 0; // length of the segments before `seg`
  for (let i = 0; i < n; i++) {
    const at = ((i + rand()) / n) * total;
    while (seg < segs.length - 1 && before + segs[seg].len < at) before += segs[seg++].len;
    const s = segs[seg];
    const f = Math.min(1, (at - before) / s.len);
    const off = (rand() * 2 - 1) * spread;
    out[i * 2] = s.x + s.dx * f - (s.dy / s.len) * off;
    out[i * 2 + 1] = s.y + s.dy * f + (s.dx / s.len) * off;
  }
  return porAngulo(out);
}

/** Before strokes.json arrives: a cloud where the crow is (the illustration covers it). */
export function nuvem(n: number, rand: () => number): Float32Array {
  const out = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) {
    const a = rand() * Math.PI * 2;
    const r = Math.sqrt(rand()) * 260;
    out[i * 2] = CENTER + Math.cos(a) * r;
    out[i * 2 + 1] = CENTER + Math.sin(a) * r;
  }
  return porAngulo(out);
}

/** Exactly AMBER_SHARE of the particles, picked once: they are amber in every shape. */
export function ambar(n: number, rand: () => number): Uint8Array {
  const marks = new Uint8Array(n);
  const want = Math.round(n * AMBER_SHARE);
  const order = Array.from({ length: n }, (_, i) => i);
  for (let i = 0; i < want; i++) {
    const j = i + Math.floor(rand() * (n - i));
    [order[i], order[j]] = [order[j], order[i]];
    marks[order[i]] = 1;
  }
  return marks;
}

export const easeInOutCubic = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x < 0.5 ? 4 * x ** 3 : 1 - (-2 * x + 2) ** 3 / 2);

/** Where a particle is at `u` (0..1) of its flight from (x0, y0) to (x1, y1): eased along the
 * line, pushed sideways by sin(πu) × BEND × `bend` (its own, -1..1) times the flight's length. */
export function voo(x0: number, y0: number, x1: number, y1: number, u: number, bend: number): [number, number] {
  const e = easeInOutCubic(u);
  const side = Math.sin(Math.PI * Math.max(0, Math.min(1, u))) * BEND * bend;
  // (-dy, dx) is perpendicular to the flight and as long as it.
  return [x0 + (x1 - x0) * e - (y1 - y0) * side, y0 + (y1 - y0) * e + (x1 - x0) * side];
}
