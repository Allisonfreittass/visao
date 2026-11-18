/** The floor of every screen: --bg and three big soft blobs in the corners (coral, lavender,
 * peach) that drift slowly; still with reduced motion. The only gradient in the app. */
export function AmbientBackground() {
  return (
    <div className="ambient" aria-hidden="true">
      <span className="ambient-blob ambient-blob--1" />
      <span className="ambient-blob ambient-blob--2" />
      <span className="ambient-blob ambient-blob--3" />
    </div>
  );
}
