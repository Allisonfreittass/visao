import { Icon, type IconName } from "../components/Icon";

export type SensorKind = "mac" | "whatsapp" | "email" | "caderno" | "projeto";

const ICONS: Record<SensorKind, IconName> = {
  mac: "laptop",
  whatsapp: "message",
  email: "mail",
  caderno: "notebook",
  projeto: "folder",
};

const LABELS: Record<SensorKind, string> = {
  mac: "Mac",
  whatsapp: "WhatsApp",
  email: "E-mail",
  caderno: "Caderno",
  projeto: "Projeto",
};

interface SensorProps {
  kind: SensorKind;
  size?: number;
  /** Disconnected: drawn in cinza instead of the text color. */
  asleep?: boolean;
  decorative?: boolean;
  label?: string;
  className?: string;
}

/** Where he reaches (Mac, e-mail, Caderno…) and each project: a line icon with a 1.5 px stroke in
 * the color of the text around it, no color of its own (DESIGN.md §2, §4). */
export function Sensor({ kind, size = 20, asleep = false, decorative = true, label, className }: SensorProps) {
  return (
    <span
      className={`sensor sensor--${kind}${asleep ? " sensor--off" : ""}${className ? ` ${className}` : ""}`}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label ?? LABELS[kind]}
    >
      <Icon name={ICONS[kind]} size={size} exact />
    </span>
  );
}
