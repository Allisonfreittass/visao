// The keyboard on iPhone: it covers the bottom of the page and iOS scrolls the whole page up to
// show the field, which left the message box floating mid-screen with a gap under it and the
// chat sliding under the clock. Instead the app takes exactly the visible height, so the box
// sits on the keyboard, and the page itself never scrolls.

/** A keyboard (or any panel) taller than this is open. */
const KEYBOARD_MIN = 120;

export function trackVisibleViewport(root: HTMLElement = document.documentElement): () => void {
  const vv = window.visualViewport;
  if (!vv) return () => undefined;
  const apply = () => {
    root.style.setProperty("--app-height", `${Math.round(vv.height)}px`);
    root.toggleAttribute("data-teclado", window.innerHeight - vv.height > KEYBOARD_MIN);
    if (window.scrollY !== 0 || vv.offsetTop !== 0) window.scrollTo(0, 0);
  };
  vv.addEventListener("resize", apply);
  vv.addEventListener("scroll", apply);
  apply();
  return () => {
    vv.removeEventListener("resize", apply);
    vv.removeEventListener("scroll", apply);
  };
}
