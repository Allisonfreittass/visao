/** Up to this, the close crop of the head (only the eye and the beak); above it, the whole icon. */
export const CORVO_SMALL_MAX = 48;

/** What the icon says when it is not beside his name. */
export const CORVO_ALT = "O corvo do VISAO, de olho âmbar";

export function corvoSrc(size: number): string {
  return size > CORVO_SMALL_MAX ? "/marca/corvo-olho.svg" : "/marca/corvo-olho-pequeno.svg";
}

/** The crow with the amber eye (DESIGN.md §5): his avatar, the sidebar logo, the call and the app
 * icon. The drawing carries its own rounded corners and paper ground; on a light page a 1 px line
 * in tinta keeps its edge (layout `.corvo`). Decorative unless `label` names it. */
export function Corvo({ size, label, className }: { size: number; label?: string; className?: string }) {
  return (
    <img
      className={`corvo${className ? ` ${className}` : ""}`}
      src={corvoSrc(size)}
      width={size}
      height={size}
      alt={label ?? ""}
      aria-hidden={label ? undefined : true}
      decoding="async"
      draggable={false}
    />
  );
}
