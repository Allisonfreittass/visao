// The keyboard on iPhone: it covers the bottom of the page and iOS scrolls the whole page up to
// show the field, which left the message box floating mid-screen with a gap under it and the
// chat sliding under the clock. Instead the app takes exactly the visible height, so the box
// sits on the keyboard, and the page itself never scrolls.
//
// Whether the keyboard is open is judged against the tallest the visible area has been (the
// screen without a keyboard): on iPhone window.innerHeight shrinks with the keyboard too, so
// comparing with it said "closed" and kept the home-bar space, a gap above the keyboard.

/** A keyboard (or any panel) taller than this is open. */
const KEYBOARD_MIN = 120;

export function trackVisibleViewport(root: HTMLElement = document.documentElement): () => void {
  const vv = window.visualViewport;
  if (!vv) return () => undefined;
  let tallest = vv.height;
  let width = vv.width;
  const apply = () => {
    // A rotation changes what "tallest" means.
    if (Math.abs(vv.width - width) > 40) {
      width = vv.width;
      tallest = vv.height;
    }
    tallest = Math.max(tallest, vv.height, root.clientHeight || 0);
    root.style.setProperty("--app-height", `${Math.round(vv.height)}px`);
    root.toggleAttribute("data-teclado", tallest - vv.height > KEYBOARD_MIN);
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
