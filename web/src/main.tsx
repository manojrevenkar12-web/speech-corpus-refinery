import "@fontsource-variable/archivo/wdth.css";
import "@fontsource/jetbrains-mono/400.css";
import "./shared/theme/global.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
