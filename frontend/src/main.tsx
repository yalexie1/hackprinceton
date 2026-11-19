import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { autoscrollEnabled, startAutoscroll } from "./lib/autoscroll";
import "./styles.css";
import "./architecture.css";
import "./readability.css";
import "./homeowner-polish.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
if (autoscrollEnabled(window)) startAutoscroll(window);
