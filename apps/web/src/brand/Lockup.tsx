import { Ciclope } from "../ciclope/Ciclope";
import type { CiclopeState } from "../ciclope/state";

/** The Ciclope beside the name: the logo of the side bar and the top bar. `data-lockup` is where
 * the opening's lockup lands (components/Intro.tsx). */
export function Lockup({ state = "idle", size = 28, animated = false }: { state?: CiclopeState; size?: number; animated?: boolean }) {
  return (
    <span className="lockup" data-lockup="">
      <Ciclope state={state} size={size} animated={animated} decorative />
      <span className="lockup-word">V<b>.</b>I<b>.</b>S<b>.</b>A<b>.</b>O<b>.</b></span>
    </span>
  );
}
