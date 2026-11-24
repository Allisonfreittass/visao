/** The 28 px bar at the bottom of the window (computer only), in Geist Mono. For now only what the
 * app already knows for sure: whether the server answers. Braço, rotinas, silêncio, tokens and the
 * model come in step 3 of docs/design/telas-visao/PROMPT_CLAUDE_CODE.md, from the API. */
export function StatusBar({ online }: { online: boolean }) {
  return (
    <footer className="status-bar" aria-label="Estado">
      <span className="status-bar-item">
        <span className={`status-bar-dot${online ? " on" : ""}`} aria-hidden="true" />
        {online ? "servidor ok" : "sem conexão com o servidor"}
      </span>
    </footer>
  );
}
