import { Anel } from "../anel/Anel";
import type { AnelEstado } from "../anel/state";

/** The ring beside the name: the logo of the side bar and the top bar. `data-lockup` is where
 * the opening's lockup lands (components/Intro.tsx). */
export function Lockup({ estado = "ocioso", size = 28, animated = false }: { estado?: AnelEstado; size?: number; animated?: boolean }) {
  return (
    <span className="lockup" data-lockup="">
      <Anel estado={estado} size={size} animated={animated} decorative />
      <span className="lockup-word">V<b>.</b>I<b>.</b>S<b>.</b>A<b>.</b>O<b>.</b></span>
    </span>
  );
}
