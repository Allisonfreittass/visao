import { useEffect, useRef } from "react";

/** While something is open (a page, the drawer, a project), Back closes it instead of leaving
 * the app: the Android back button, the browser's back, and the gesture where the system has one.
 * Closing it by its own button takes the history entry back out. */
export function useBackClose(open: boolean, onClose: () => void): void {
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    if (!open) return;
    const token = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    let pushed = false;
    let popped = false;
    const onPop = () => {
      popped = true;
      close.current();
    };
    // Pushed a tick later: an effect that mounts and unmounts at once (React's strict mode, a
    // panel closed as it opens) never leaves an entry behind whose Back would close the next one.
    const timer = window.setTimeout(() => {
      window.history.pushState({ ...(window.history.state ?? {}), visaoOverlay: token }, "");
      pushed = true;
      window.addEventListener("popstate", onPop);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("popstate", onPop);
      if (pushed && !popped && window.history.state?.visaoOverlay === token) window.history.back();
    };
  }, [open]);
}
