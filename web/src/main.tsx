import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Shell } from "./app/Shell";
import "./app/shell.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Shell />
  </StrictMode>,
);
