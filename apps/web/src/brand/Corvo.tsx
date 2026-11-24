/** Above this, the detailed drawing; at or below it, the small one, with thicker strokes. */
export const CORVO_SMALL_MAX = 72;

export function corvoSrc(size: number): string {
  return size > CORVO_SMALL_MAX ? "/marca/corvo-512.png" : "/marca/corvo-256.png";
}

/** The crow in the eclipse (DESIGN.md §5): his avatar, the sidebar logo and the app icon. The
 * picture carries its own rounded corners. Decorative unless `label` names it. */
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
