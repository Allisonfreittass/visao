/** A few line icons drawn for the rail and the panels: 1.5px strokes in the text color. */
const PATHS = {
  chat: "M4 5h16v11H9l-5 4z",
  inbox: "M4 13l2.5-7h11L20 13v6H4zM4 13h5l1 2h4l1-2h5",
  notebook: "M6 3h12v18H6zM9 3v18M12 8h4M12 12h4",
  laptop: "M5 5h14v10H5zM2 19h20",
  sliders: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4",
  plus: "M12 5v14M5 12h14",
  menu: "M4 7h16M4 12h16M4 17h10",
  folder: "M3 6h6l2 2h10v11H3z",
  reply: "M9 15L4 10l5-5M4 10h10a6 6 0 0 1 6 6v2",
  phone: "M6 3l3 1 1.5 4-2 1.5a11 11 0 0 0 6 6l1.5-2 4 1.5 1 3-2 2C11 20 4 13 4 5z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}
