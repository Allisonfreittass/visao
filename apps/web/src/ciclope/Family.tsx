import { hash01 } from "./model";

export type CritterKind = "mac" | "whatsapp" | "email" | "caderno" | "projeto";

/** The sensors' colors, one per integration. */
export const FAMILY_COLORS: Record<Exclude<CritterKind, "projeto">, string> = {
  mac: "#3B6BFF",
  whatsapp: "#18C27A",
  email: "#E0A800",
  caderno: "#9B87FF",
};

/** Colors a project's sensor can take, picked by its name so it never changes (no red: red is
 * the mascot's). */
const PROJECT_COLORS = ["#3B6BFF", "#18C27A", "#E0A800", "#9B87FF", "#14B8C4", "#8E9AAF"];

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

interface CritterProps {
  kind: CritterKind;
  size?: number;
  /** For "projeto": its color (projectColor(name)). */
  color?: string;
  /** Disconnected: the sensor's eye goes dark (opacity .2). */
  asleep?: boolean;
  decorative?: boolean;
  label?: string;
  className?: string;
}

/** A sensor: the mascot's family, one per integration (Mac, e-mail…) and one per project. A
 * graphite block with a colored rim and one colored eye. Named Critter from before. */
export function Critter({ kind, size = 24, color, asleep, decorative = true, label, className }: CritterProps) {
  const fill = color ?? (kind === "projeto" ? FAMILY_COLORS.caderno : FAMILY_COLORS[kind]);
  return (
    <svg
      className={`critter sensor sensor--${kind}${className ? ` ${className}` : ""}`}
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label ?? LABELS[kind]}
      focusable="false"
    >
      <rect width="100" height="100" rx="30" fill="#24252B" />
      <rect x="2" y="2" width="96" height="96" rx="28" fill="none" stroke={fill} strokeOpacity=".6" strokeWidth="4" />
      <circle cx="50" cy="50" r="24" fill="#050506" />
      <g style={{ opacity: asleep ? 0.2 : 1 }}>
        <circle cx="50" cy="50" r="11" fill={fill} />
        <circle cx="50" cy="50" r="4.5" fill="#050506" />
      </g>
    </svg>
  );
}
