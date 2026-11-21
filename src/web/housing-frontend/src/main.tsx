import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// Phông tự host (chạy offline), chỉ subset latin + vietnamese và các weight đang dùng.
import "@fontsource/be-vietnam-pro/latin-400.css";
import "@fontsource/be-vietnam-pro/vietnamese-400.css";
import "@fontsource/be-vietnam-pro/latin-500.css";
import "@fontsource/be-vietnam-pro/vietnamese-500.css";
import "@fontsource/be-vietnam-pro/latin-600.css";
import "@fontsource/be-vietnam-pro/vietnamese-600.css";
import "@fontsource/lora/latin-500.css";
import "@fontsource/lora/vietnamese-500.css";
import "@fontsource/lora/latin-600.css";
import "@fontsource/lora/vietnamese-600.css";
import "./styles.css";

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
