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

/**
 * The iPhone app installed from the home screen has a bug: after the keyboard opens once, the
 * page stays shorter (innerHeight and 100dvh drop by about the home-bar area) until the app is
 * force-quit, and the system paints that space as a black strip at the bottom. Hiding the app
 * for one reflow and showing it again makes iOS measure the screen again. The lists inside keep
 * where they were scrolled to. Does nothing when the page has its full height.
 */
export function healShrunkViewport(tallestInner: number, el: HTMLElement | null): boolean {
  if (!el || tallestInner - window.innerHeight <= 4) return false;
  const scrolled = Array.from(el.querySelectorAll<HTMLElement>("*")).filter((n) => n.scrollTop > 0).map((n) => [n, n.scrollTop] as const);
  el.style.display = "none";
  void el.offsetHeight;
  el.style.display = "";
  for (const [n, top] of scrolled) n.scrollTop = top;
  return true;
}

export function trackVisibleViewport(root: HTMLElement = document.documentElement): () => void {
  const vv = window.visualViewport;
  if (!vv) return () => undefined;
  let tallest = vv.height;
  let width = vv.width;
  let tallestInner = window.innerHeight;
  let wasKeyboard = false;
  const apply = () => {
    // A rotation changes what "tallest" means.
    if (Math.abs(vv.width - width) > 40) {
      width = vv.width;
      tallest = vv.height;
      tallestInner = window.innerHeight;
    }
    tallest = Math.max(tallest, vv.height, root.clientHeight || 0);
    const keyboard = tallest - vv.height > KEYBOARD_MIN;
    // Keyboard open: exactly the visible height, so the box sits on it. Closed: the CSS height
    // (100dvh). In the app installed on the iPhone the visible height already leaves out the
    // home-bar area, which the page pads for again, and the box floated that much too high.
    if (keyboard) root.style.setProperty("--app-height", `${Math.round(vv.height)}px`);
    else root.style.removeProperty("--app-height");
    root.toggleAttribute("data-teclado", keyboard);
    if (!keyboard) tallestInner = Math.max(tallestInner, window.innerHeight);
    if (wasKeyboard && !keyboard && typeof document !== "undefined") {
      setTimeout(() => healShrunkViewport(tallestInner, document.getElementById("root")), 140);
    }
    wasKeyboard = keyboard;
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
