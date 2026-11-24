/** The seal (DESIGN.md §1): the amber field with VISAO in Six Caps filling the square behind the
 * woodcut bust. Only on the login and brand material, never as the app icon. Decorative. */
export function Selo({ className }: { className?: string }) {
  return (
    <div className={`selo${className ? ` ${className}` : ""}`} aria-hidden="true">
      <svg viewBox="0 0 600 600" className="selo-nome">
        <text x="6" y="528" textLength="588" lengthAdjust="spacingAndGlyphs">VISAO</text>
      </svg>
      <img className="selo-busto" src="/marca/muninn-busto.webp" alt="" decoding="async" draggable={false} />
    </div>
  );
}
