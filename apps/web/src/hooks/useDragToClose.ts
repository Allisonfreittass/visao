import { type PointerEvent, useRef, useState } from "react";

/** A panel you close by dragging it the way it came from (down for a sheet, left for a drawer),
 * like the system's own sheets. Touch and pen only; a short drag springs back. */
export function useDragToClose(direction: "down" | "left", onClose: () => void, threshold = 110) {
  const [offset, setOffset] = useState(0);
  const start = useRef<{ x: number; y: number; on: boolean } | null>(null);

  const along = (e: PointerEvent) => {
    const s = start.current!;
    return direction === "down" ? e.clientY - s.y : s.x - e.clientX;
  };
  const across = (e: PointerEvent) => {
    const s = start.current!;
    return direction === "down" ? e.clientX - s.x : e.clientY - s.y;
  };

  return {
    offset,
    handlers: {
      onPointerDown(e: PointerEvent<HTMLElement>) {
        if (e.pointerType === "mouse") return;
        start.current = { x: e.clientX, y: e.clientY, on: false };
      },
      onPointerMove(e: PointerEvent<HTMLElement>) {
        if (!start.current) return;
        const d = along(e);
        if (!start.current.on) {
          if (d > 10 && d > Math.abs(across(e)) * 1.4) {
            start.current.on = true;
            e.currentTarget.setPointerCapture(e.pointerId);
          } else if (Math.abs(across(e)) > 10) {
            start.current = null;
          }
          return;
        }
        setOffset(Math.max(0, d));
      },
      onPointerUp() {
        const closing = start.current?.on && offset > threshold;
        start.current = null;
        setOffset(0);
        if (closing) onClose();
      },
      onPointerCancel() {
        start.current = null;
        setOffset(0);
      },
    },
  };
}
