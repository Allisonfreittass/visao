import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { applyTheme } from "./brand/theme";
import { trackVisibleViewport } from "./viewport";
import "./styles.css";
import "./layout.css";

// Before the first paint, so whoever picked Tinta or Rótulo never sees Papel flash first.
applyTheme();

trackVisibleViewport();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
