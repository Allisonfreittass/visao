import { useEffect, useState } from "react";

/** True on screens wide enough for the three columns (computer); false on phones and tablets. */
export function useWide(minWidth = 1180): boolean {
  const query = `(min-width: ${minWidth}px)`;
  const [wide, setWide] = useState(() => typeof window !== "undefined" && !!window.matchMedia?.(query).matches);
  useEffect(() => {
    const list = window.matchMedia?.(query);
    if (!list) return;
    const onChange = () => setWide(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return wide;
}
