import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyTheme, followSystemTheme } from "./brand/theme";
import { trackVisibleViewport } from "./viewport";
import "./styles.css";
import "./layout.css";

// Before the first paint, so a dark-theme owner never sees the light theme flash first.
applyTheme();
followSystemTheme();

trackVisibleViewport();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
