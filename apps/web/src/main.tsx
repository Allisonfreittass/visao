import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { loadPreference } from "./session";
import { trackVisibleViewport } from "./viewport";
import "./styles.css";
import "./ceu.css";

// Before the first paint, so the "Céu" appearance never flashes the night theme first.
document.documentElement.dataset.theme = loadPreference("appearance") === "noite" ? "noite" : "ceu";

trackVisibleViewport();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
