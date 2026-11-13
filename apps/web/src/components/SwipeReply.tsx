import { type PointerEvent, type ReactNode, useRef, useState } from "react";

import { Icon } from "./Icon";

/** Past this, letting go answers the message (WhatsApp-like). */
const TRIGGER = 56;
const MAX = 84;

interface SwipeReplyProps {
  id: string;
  className: string;
  disabled?: boolean;
  onReply: () => void;
  children: ReactNode;
}

/** A message you drag to the right to answer it. Vertical scrolling stays the browser's
 * (touch-action: pan-y); only a clearly sideways drag moves the bubble. Touch and pen only: with a
 * mouse, the Responder button shows on hover. */
export function SwipeReply({ id, className, disabled, onReply, children }: SwipeReplyProps) {
  const [dx, setDx] = useState(0);
  const start = useRef<{ x: number; y: number; mode: "pending" | "swipe" | "none" } | null>(null);
  const armed = useRef(false);

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (disabled || e.pointerType === "mouse") return;
    start.current = { x: e.clientX, y: e.clientY, mode: "pending" };
    armed.current = false;
  }

  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const s = start.current;
    if (!s || s.mode === "none") return;
    const moveX = e.clientX - s.x;
    const moveY = e.clientY - s.y;
    if (s.mode === "pending") {
      if (Math.abs(moveY) > 10 && Math.abs(moveY) > Math.abs(moveX)) {
        s.mode = "none";
        return;
      }
      if (moveX > 10 && moveX > Math.abs(moveY) * 1.5) {
        s.mode = "swipe";
        e.currentTarget.setPointerCapture(e.pointerId);
      } else {
        return;
      }
    }
    // Resistance after the trigger point, like a spring.
    const next = moveX <= TRIGGER ? Math.max(0, moveX) : Math.min(MAX, TRIGGER + (moveX - TRIGGER) * 0.35);
    if (next >= TRIGGER && !armed.current) {
      armed.current = true;
      navigator.vibrate?.(8);
    } else if (next < TRIGGER) {
      armed.current = false;
    }
    setDx(next);
  }

  function finish() {
    const swiped = start.current?.mode === "swipe" && armed.current;
    start.current = null;
    armed.current = false;
    setDx(0);
    if (swiped) onReply();
  }

  return (
    <div
      id={id}
      className={`${className}${dx > 0 ? " bubble--swiping" : ""}`}
      style={dx > 0 ? { transform: `translateX(${dx}px)` } : undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finish}
      onPointerCancel={finish}
    >
      {dx > 0 && (
        <span
          className={`swipe-reply-icon${dx >= TRIGGER ? " swipe-reply-icon--armed" : ""}`}
          // Centered in the gap the drag opens, which is dx wide, left of the moving bubble.
          style={{ opacity: Math.min(1, dx / TRIGGER), transform: `translateX(${-dx / 2 - 15}px) scale(${0.6 + 0.4 * Math.min(1, dx / TRIGGER)})` }}
          aria-hidden="true"
        >
          <Icon name="reply" size={16} />
        </span>
      )}
      {children}
    </div>
  );
}
