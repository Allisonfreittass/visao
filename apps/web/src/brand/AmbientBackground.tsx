import type { CiclopeState } from "../ciclope/state";

/** The floor of every screen: --bg, a HUD grid of faint dots, and the sensor's red glow behind
 * the mascot of Início, which breathes with its state (still with reduced motion). */
export function AmbientBackground({ state = "idle" }: { state?: CiclopeState }) {
  return (
    <div className="ambient" data-state={state} aria-hidden="true">
      <span className="ambient-grid" />
      <span className="ambient-glow" />
    </div>
  );
}
