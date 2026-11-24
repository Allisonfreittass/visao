/** Line icons: 1.5 px strokes in the text color. The ones the new screens use come from the mockup
 * (docs/design/telas-visao), drawn on a 20-unit grid; the older ones stay on 24. */
const PATHS_20 = {
  home: "M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4.5h-5V17H4a1 1 0 0 1-1-1z",
  chat: "M4 5h12v8H9l-4 3v-3H4z",
  folder: "M3 6a1 1 0 0 1 1-1h4l2 2h6a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z",
  notebook: "M5 3.5h9a1 1 0 0 1 1 1V17H6a1 1 0 0 1-1-1zM5 14.5h10M8 3.5v11",
  clock: "M3 10a7 7 0 1 0 14 0a7 7 0 1 0 -14 0M10 6v4l3 2",
  laptop: "M5 5h10v7H5zM3 15h14",
  agents: "M3.8 7a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0 -4.4 0M11.8 7a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0 -4.4 0M7.8 13.5a2.2 2.2 0 1 0 4.4 0a2.2 2.2 0 1 0 -4.4 0M7.5 8.6 9 11.8M12.5 8.6 11 11.8",
  plug: "M7 3v4M13 3v4M5 7h10v3a5 5 0 0 1-10 0zM10 15v3",
  sparkle: "M10 3v4M10 13v4M3 10h4M13 10h4M5.5 5.5l2 2M12.5 12.5l2 2M14.5 5.5l-2 2M7.5 12.5l-2 2",
  search: "M4 9a5 5 0 1 0 10 0a5 5 0 1 0 -10 0M13 13l4 4",
  plus: "M10 4v12M4 10h12",
  gear: "M7.5 10a2.5 2.5 0 1 0 5.0 0a2.5 2.5 0 1 0 -5.0 0M10 3v2M10 15v2M3 10h2M15 10h2M5 5l1.4 1.4M13.6 13.6 15 15M5 15l1.4-1.4M13.6 6.4 15 5",
  mic: "M7.5 5.5a2.5 2.5 0 0 1 5 0v4a2.5 2.5 0 0 1-5 0zM5 10a5 5 0 0 0 10 0M10 15v2",
  send: "M10 16V5M5.5 9.5 10 5l4.5 4.5",
  pin: "M7 3h6l-1 5 3 3H5l3-3zM10 11v6",
  speaker: "M4 8h3l4-3v10l-4-3H4zM14 7.5a3.5 3.5 0 0 1 0 5",
  panel: "M4 4h12a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM12 4v12",
  share: "M10 3v9M6.5 6.5 10 3l3.5 3.5M4 11v4a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-4",
  link: "M8.5 11.5a3 3 0 0 0 4.2 0l2.6-2.6a3 3 0 0 0-4.2-4.2l-1 1M11.5 8.5a3 3 0 0 0-4.2 0l-2.6 2.6a3 3 0 0 0 4.2 4.2l1-1",
  file: "M5 3h6l4 4v10H5zM11 3v4h4",
  download: "M10 3v10M6 9.5l4 4 4-4M4 17h12",
  command: "M7 7h6v6H7zM7 7V5.5A1.5 1.5 0 1 0 5.5 7H7M13 7V5.5A1.5 1.5 0 1 1 14.5 7H13M7 13v1.5A1.5 1.5 0 1 1 5.5 13H7M13 13v1.5a1.5 1.5 0 1 0 1.5-1.5H13",
} as const;

const PATHS_24 = {
  inbox: "M4 13l2.5-7h11L20 13v6H4zM4 13h5l1 2h4l1-2h5",
  sliders: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4",
  menu: "M4 7h16M4 12h16M4 17h10",
  back: "M15 5l-7 7 7 7",
  reply: "M9 15L4 10l5-5M4 10h10a6 6 0 0 1 6 6v2",
  phone: "M6 3l3 1 1.5 4-2 1.5a11 11 0 0 0 6 6l1.5-2 4 1.5 1 3-2 2C11 20 4 13 4 5z",
  camera: "M3 8h4l2-3h6l2 3h4v11H3zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  flip: "M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M18 3v4h-4M6 21v-4h4",
  close: "M6 6l12 12M18 6L6 18",
  plane: "M10.5 13.5L3 11l1.5-1.5 8 1 4-4.5a2 2 0 0 1 3 3l-4.5 4 1 8L14.5 22 12 14.5l-3.5 3.5V20l-1.5 1-1-3-3-1 1-1.5h2z",
  coin: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM14.5 9.5c-.5-1-1.4-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1.1 0-2-.5-2.5-1.5M12 6.5V8M12 16v1.5",
  bed: "M3 18V7M3 13h18v5M21 13a3 3 0 0 0-3-3h-7v3M7 11.5a1.5 1.5 0 1 0 0-.01",
  mail: "M3 6h18v12H3zM3 7l9 6.5L21 7",
  message: "M12 4a8 8 0 0 0-6.9 12L4 20l4.1-1.1A8 8 0 1 0 12 4z",
} as const;

export type IconName = keyof typeof PATHS_20 | keyof typeof PATHS_24;

function shape(name: IconName): { d: string; box: number } {
  return name in PATHS_20
    ? { d: PATHS_20[name as keyof typeof PATHS_20], box: 20 }
    : { d: PATHS_24[name as keyof typeof PATHS_24], box: 24 };
}

/** `exact`: the stroke stays 1.5 px whatever the size (the sensors, DESIGN.md §4). */
export function Icon({ name, size = 18, exact = false, className }: { name: IconName; size?: number; exact?: boolean; className?: string }) {
  const { d, box } = shape(name);
  return (
    <svg className={`icon${className ? ` ${className}` : ""}`} width={size} height={size} viewBox={`0 0 ${box} ${box}`} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
      <path d={d} vectorEffect={exact ? "non-scaling-stroke" : undefined} />
    </svg>
  );
}
