import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import PullToRefresh from "./components/PullToRefresh";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <PullToRefresh />
    <App />
  </StrictMode>,
);
