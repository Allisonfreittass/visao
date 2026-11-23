/** A few line icons drawn for the rail and the panels: 1.5px strokes in the text color. */
const PATHS = {
  chat: "M4 5h16v11H9l-5 4z",
  inbox: "M4 13l2.5-7h11L20 13v6H4zM4 13h5l1 2h4l1-2h5",
  notebook: "M6 3h12v18H6zM9 3v18M12 8h4M12 12h4",
  laptop: "M5 5h14v10H5zM2 19h20",
  sliders: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4",
  plus: "M12 5v14M5 12h14",
  menu: "M4 7h16M4 12h16M4 17h10",
  back: "M15 5l-7 7 7 7",
  folder: "M3 6h6l2 2h10v11H3z",
  reply: "M9 15L4 10l5-5M4 10h10a6 6 0 0 1 6 6v2",
  phone: "M6 3l3 1 1.5 4-2 1.5a11 11 0 0 0 6 6l1.5-2 4 1.5 1 3-2 2C11 20 4 13 4 5z",
  camera: "M3 8h4l2-3h6l2 3h4v11H3zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  flip: "M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4",
  home: "M4 11l8-7 8 7v9h-5v-6H9v6H4z",
  gear: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2.5v3M12 18.5v3M4.2 6.2l2.1 2.1M17.7 15.7l2.1 2.1M2.5 12h3M18.5 12h3M4.2 17.8l2.1-2.1M17.7 8.3l2.1-2.1",
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21",
  send: "M12 19V5M5.5 11.5L12 5l6.5 6.5",
  close: "M6 6l12 12M18 6L6 18",
  plane: "M10.5 13.5L3 11l1.5-1.5 8 1 4-4.5a2 2 0 0 1 3 3l-4.5 4 1 8L14.5 22 12 14.5l-3.5 3.5V20l-1.5 1-1-3-3-1 1-1.5h2z",
  coin: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM14.5 9.5c-.5-1-1.4-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1.1 0-2-.5-2.5-1.5M12 6.5V8M12 16v1.5",
  bed: "M3 18V7M3 13h18v5M21 13a3 3 0 0 0-3-3h-7v3M7 11.5a1.5 1.5 0 1 0 0-.01",
  mail: "M3 6h18v12H3zM3 7l9 6.5L21 7",
  message: "M12 4a8 8 0 0 0-6.9 12L4 20l4.1-1.1A8 8 0 1 0 12 4z",
} as const;

export type IconName = keyof typeof PATHS;

/** `exact`: the stroke stays 1.5 px whatever the size (the sensors, DESIGN.md §4). */
export function Icon({ name, size = 18, exact = false, className }: { name: IconName; size?: number; exact?: boolean; className?: string }) {
  return (
    <svg className={`icon${className ? ` ${className}` : ""}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
      <path d={PATHS[name]} vectorEffect={exact ? "non-scaling-stroke" : undefined} />
    </svg>
  );
}
