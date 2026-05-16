import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import App from "./App";
import { ToastProvider } from "./components/ui";

createRoot(document.getElementById("root")).render(
  <ToastProvider>
    <App />
  </ToastProvider>
);
