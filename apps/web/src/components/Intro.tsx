import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import { Genesis } from "../muninn/Genesis";
import { T_CURTA } from "../muninn/genesis.logic";
import { loadPreference, savePreference } from "../session";

/** How long the opening lasts, end to end. */
export const INTRO_MS = 2400;
const DAY_KEY = "intro-day";
const SESSION_KEY = "visao.intro-ran";
const EASE = "cubic-bezier(.2, .8, .2, 1)";

/** "Bom dia" / "Boa tarde" / "Boa noite", by the hour on this device. */
export function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "Bom dia";
  if (hour >= 12 && hour < 18) return "Boa tarde";
  return "Boa noite";
}

function localDay(now: Date): string {
  return `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`;
}

function ranThisSession(): boolean {
  try {
    return sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** The opening plays on the first open of the day (once per tab session), and never for
 * someone who asked the system for less motion. */
export function shouldPlayIntro(now: Date, lastDay: string | null, reduced: boolean, ranInSession = false): boolean {
  return !reduced && !ranInSession && lastDay !== localDay(now);
}

export function introDue(now = new Date()): boolean {
  return shouldPlayIntro(now, loadPreference(DAY_KEY), reducedMotion(), ranThisSession());
}

/** Right after logging in it plays too, unless it already did in this tab. */
export function introAfterLogin(): boolean {
  return !reducedMotion() && !ranThisSession();
}

const WORD = "V.I.S.A.O.";

/** The opening (≈2.4 s), a short genesis of Muninn (DESIGN.md §6, T_CURTA): the amber dot at the
 * chest, the strokes growing out of it, the illustration and its eye, the ring closing from the
 * gap and the gap's flash, all by 1.45 s; then Muninn slides left and the name is typed beside
 * it, and the lockup flies to the side bar's logo as the app shows through.
 * A click or a key skips it. */
export function Intro({ onDone }: { onDone: () => void }) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    savePreference(DAY_KEY, localDay(new Date()));
    try {
      sessionStorage.setItem(SESSION_KEY, "1");
    } catch {
      // Without storage it may play again in this tab; harmless.
    }
    const el = root.current;
    if (!el) return;
    const q = <T extends Element>(s: string) => el.querySelector(s) as T;
    const all = <T extends Element>(s: string) => Array.from(el.querySelectorAll(s)) as T[];
    const anims: Animation[] = [];
    const run = (node: Element | null, frames: Keyframe[], options: KeyframeAnimationOptions) => {
      if (!node) return;
      anims.push(node.animate(frames, { fill: "both", ...options }));
    };

    // 1–3. The genesis plays by itself in the canvas (Genesis, T_CURTA).

    // 4. Muninn slides left and the name is typed, 40 ms a letter.
    const lockup = q<HTMLElement>(".intro-lockup");
    const word = q<HTMLElement>(".intro-word");
    const shift = word ? (word.offsetWidth + 20) / 2 : 0;
    if (lockup) lockup.style.transform = `translateX(${shift}px)`;
    run(lockup, [{ transform: `translateX(${shift}px)` }, { transform: "translateX(0)" }], { delay: 1500, duration: 400, easing: EASE });
    all<HTMLElement>(".intro-word > span").forEach((letter, i) => {
      run(letter, [{ opacity: 0 }, { opacity: 1 }], { delay: 1520 + i * 40, duration: 1, easing: "linear" });
    });

    // 5. The lockup flies to the side bar's logo; the app shows through.
    const fly = window.setTimeout(() => {
      if (!lockup) return;
      const from = lockup.getBoundingClientRect();
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-lockup]")).find((n) => n.offsetParent !== null);
      const to = target?.getBoundingClientRect() ?? new DOMRect(24, 20, 140, 28);
      const scale = to.height / from.height;
      lockup.style.transformOrigin = "0 0";
      run(lockup, [{ transform: "translate(0, 0) scale(1)" }, { transform: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${scale})` }], { duration: 420, easing: EASE, fill: "forwards" });
    }, 1920);
    run(el, [{ opacity: 1 }, { opacity: 0 }], { delay: 2020, duration: 380, easing: "ease-in", fill: "forwards" });
    const done = window.setTimeout(onDone, INTRO_MS);

    const skip = () => onDone();
    window.addEventListener("keydown", skip);
    return () => {
      window.clearTimeout(fly);
      window.clearTimeout(done);
      window.removeEventListener("keydown", skip);
      anims.forEach((a) => a.cancel());
    };
  }, [onDone]);

  // On <body>, so no app layout rule can pull it out of full screen.
  return createPortal(
    <div className="intro" ref={root} onClick={onDone} aria-hidden="true">
      <div className="intro-stage">
        <div className="intro-lockup">
          <div className="intro-hero">
            {/* The assets are usually cached by the login; if not, the ring still closes on time. */}
            <Genesis timeline={T_CURTA} assetWaitMs={250} />
          </div>
          <span className="intro-word">
            {WORD.split("").map((c, i) => (c === "." ? <span key={i}><b>.</b></span> : <span key={i}>{c}</span>))}
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
