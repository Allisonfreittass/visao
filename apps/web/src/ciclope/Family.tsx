import { useId } from "react";

import { hash01 } from "./model";

export type CritterKind = "mac" | "whatsapp" | "email" | "caderno" | "projeto";

export const FAMILY_COLORS: Record<Exclude<CritterKind, "projeto">, string> = {
  mac: "#3B6BFF",
  whatsapp: "#18C27A",
  email: "#FFC83D",
  caderno: "#9B87FF",
};

/** Colors a project's critter can take, picked by its name so it never changes. */
const PROJECT_COLORS = ["#FF6A1A", "#3B6BFF", "#18C27A", "#FFC83D", "#9B87FF", "#FF5C8A", "#14B8C4"];

export function projectColor(name: string): string {
  return PROJECT_COLORS[Math.floor(hash01(name.trim().toLowerCase()) * PROJECT_COLORS.length)];
}

const LABELS: Record<CritterKind, string> = {
  mac: "Mac",
  whatsapp: "WhatsApp",
  email: "E-mail",
  caderno: "Caderno",
  projeto: "Projeto",
};

interface Shape {
  body: string;
  eye: { cx: number; cy: number; r: number };
  extra?: string;
}

// Same language as the Ciclope (flat body, soft top light, one big eye), in other shapes.
const SHAPES: Record<CritterKind, Shape> = {
  mac: {
    // a screen on a small stand
    body: "M14 12 H86 A12 12 0 0 1 98 24 V66 A12 12 0 0 1 86 78 H14 A12 12 0 0 1 2 66 V24 A12 12 0 0 1 14 12 Z M40 78 H60 L63 90 H37 Z M28 90 H72 A4 4 0 0 1 72 98 H28 A4 4 0 0 1 28 90 Z",
    eye: { cx: 50, cy: 44, r: 19 },
  },
  whatsapp: {
    // a speech bubble with its tail down-left
    body: "M50 6 C76 6 96 24 96 48 C96 72 76 90 50 90 C42 90 35 88 29 85 L8 94 L15 74 C8 67 4 58 4 48 C4 24 24 6 50 6 Z",
    eye: { cx: 51, cy: 47, r: 20 },
  },
  email: {
    // a rounded envelope
    body: "M16 18 H84 A14 14 0 0 1 98 32 V76 A14 14 0 0 1 84 90 H16 A14 14 0 0 1 2 76 V32 A14 14 0 0 1 16 18 Z",
    eye: { cx: 50, cy: 58, r: 17 },
    extra: "M8 26 L50 52 L92 26",
  },
  caderno: {
    // a sheet with a folded corner
    body: "M20 2 H66 L90 26 V88 A10 10 0 0 1 80 98 H20 A10 10 0 0 1 10 88 V12 A10 10 0 0 1 20 2 Z",
    eye: { cx: 50, cy: 50, r: 19 },
    extra: "M66 2 V20 A6 6 0 0 0 72 26 H90",
  },
  projeto: {
    body: "M30 4 H70 C86 4 96 14 96 30 V70 C96 86 86 96 70 96 H30 C14 96 4 86 4 70 V30 C4 14 14 4 30 4 Z",
    eye: { cx: 50, cy: 47, r: 21 },
  },
};

interface CritterProps {
  kind: CritterKind;
  size?: number;
  /** For "projeto": its color (projectColor(name)). */
  color?: string;
  /** Asleep: the eye is a closed line (the Mac offline). */
  asleep?: boolean;
  /** Where the iris looks, -1..1 on each axis. */
  look?: { x: number; y: number };
  decorative?: boolean;
  label?: string;
  className?: string;
}

/** A mini character of the Ciclope's family: one per integration (Mac, WhatsApp, e-mail,
 * Caderno) and one per project. */
export function Critter({ kind, size = 24, color, asleep, look = { x: 0.25, y: -0.2 }, decorative = true, label, className }: CritterProps) {
  const uid = useId().replace(/:/g, "");
  const shape = SHAPES[kind];
  const fill = color ?? (kind === "projeto" ? FAMILY_COLORS.caderno : FAMILY_COLORS[kind]);
  const { cx, cy, r } = shape.eye;
  const ir = r * 0.52;
  const ix = cx + look.x * r * 0.28;
  const iy = cy + look.y * r * 0.28;
  const shade = `critter-shade-${uid}`;
  return (
    <svg
      className={`critter critter--${kind}${className ? ` ${className}` : ""}`}
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label ?? LABELS[kind]}
      focusable="false"
    >
      <defs>
        <linearGradient id={shade} x1="0" y1="0" x2="0" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" stopOpacity=".3" />
          <stop offset=".45" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity=".28" />
        </linearGradient>
      </defs>
      <path d={shape.body} fill={fill} />
      <path d={shape.body} fill={`url(#${shade})`} />
      {shape.extra && <path d={shape.extra} fill="none" stroke="#000" strokeOpacity=".22" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />}
      {asleep ? (
        <path d={`M${cx - r * 0.7} ${cy} Q${cx} ${cy + r * 0.55} ${cx + r * 0.7} ${cy}`} fill="none" stroke="#000" strokeOpacity=".5" strokeWidth="4" strokeLinecap="round" />
      ) : (
        <>
          <circle cx={cx} cy={cy + 2.5} r={r} fill="#000" opacity=".18" />
          <circle cx={cx} cy={cy} r={r} fill="#fff" />
          <circle cx={ix} cy={iy} r={ir} fill="#1B1E3A" />
          <circle cx={ix} cy={iy} r={ir * 0.45} fill="#05060C" />
          <circle cx={ix + ir * 0.38} cy={iy - ir * 0.38} r={ir * 0.27} fill="#fff" />
        </>
      )}
    </svg>
  );
}
