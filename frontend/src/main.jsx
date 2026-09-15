import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import App from "./App";
import { ToastProvider } from "./components/ui";
import PWAController from "./components/PWAController";

createRoot(document.getElementById("root")).render(
  <ToastProvider>
    <App />
    <PWAController />
  </ToastProvider>
);
