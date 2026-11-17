import { type CSSProperties, useEffect, useMemo } from "react";
import { createPortal } from "react-dom";

import { Orb } from "../orb/Orb";
import { loadPreference, savePreference } from "../session";

/** How long the opening lasts, end to end (the CSS timeline in styles.css adds up to this). */
export const INTRO_MS = 1900;
const DAY_KEY = "intro-day";

/** "Bom dia" / "Boa tarde" / "Boa noite", by the hour on this device. */
export function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Bom dia";
  if (hour >= 12 && hour < 18) return "Boa tarde";
  return "Boa noite";
}

function localDay(now: Date): string {
  return `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`;
}

/** The opening plays once a day, and never for someone who asked the system for less motion. */
export function shouldPlayIntro(now: Date, lastDay: string | null, reducedMotion: boolean): boolean {
  return !reducedMotion && lastDay !== localDay(now);
}

export function introDue(now = new Date()): boolean {
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return shouldPlayIntro(now, loadPreference(DAY_KEY), Boolean(reduced));
}

interface Dot {
  style: CSSProperties;
  warm: boolean;
}

function scatter(count: number): Dot[] {
  return Array.from({ length: count }, (_, i) => {
    const angle = Math.random() * Math.PI * 2;
    const far = 55 + Math.random() * 25; // vmax: from beyond the edges
    const near = Math.sqrt(Math.random()) * 46; // px: onto the orb
    const turn = angle + (Math.random() - 0.5) * 1.2;
    const size = 3 + Math.random() * 4;
    return {
      warm: i % 8 === 0,
      style: {
        "--fx": `${Math.cos(angle) * far}vmax`,
        "--fy": `${Math.sin(angle) * far}vmax`,
        "--tx": `${Math.cos(turn) * near}px`,
        "--ty": `${Math.sin(turn) * near}px`,
        "--d": `${Math.round(Math.random() * 200)}ms`,
        width: size,
        height: size,
      } as CSSProperties,
    };
  });
}

/** The opening: points drift in from the edges and become the orb, a ring pulses, the name is
 * written beside it with a greeting, and the app shows through. A tap or a key skips it. */
export function Intro({ onDone }: { onDone: () => void }) {
  const dots = useMemo(() => scatter(44), []);
  const hello = useMemo(() => greeting(new Date().getHours()), []);

  useEffect(() => {
    savePreference(DAY_KEY, localDay(new Date()));
    const timer = window.setTimeout(onDone, INTRO_MS);
    const skip = () => onDone();
    window.addEventListener("keydown", skip);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", skip);
    };
  }, [onDone]);

  // On <body>, so no app layout rule (the sky's stacking) can pull it out of full screen.
  return createPortal(
    <div className="intro" onClick={onDone} aria-hidden="true">
      <div className="intro-stage">
        <div className="intro-orb">
          {dots.map((dot, i) => (
            <span key={i} className={`intro-dot${dot.warm ? " intro-dot--warm" : ""}`} style={dot.style} />
          ))}
          <span className="intro-ring" />
          <div className="intro-core">
            <Orb state="IDLE" size={132} />
          </div>
        </div>
        <div className="intro-words">
          <span className="intro-brand">V.I.S.A.O.</span>
          <p className="intro-hello">
            {hello}. <em>O que a gente resolve hoje?</em>
          </p>
        </div>
      </div>
    </div>,
    document.body,
  );
}
