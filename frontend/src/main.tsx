import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { getToken, setToken } from "./api/client";
import "./index.css";
import "./lib/install";

async function enableDemoApi() {
  if (!import.meta.env.DEV || import.meta.env.VITE_MOCK_API !== "1") return;
  const { setupWorker } = await import("msw/browser");
  const { handlers } = await import("./mocks/handlers");
  await setupWorker(...handlers).start({ onUnhandledRequest: "bypass", quiet: true });
  // demo mode: already logged in
  if (!getToken()) setToken("demo-token");
}

// lets phones install the site as an app (not in dev: it would cache the dev server)
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

enableDemoApi().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
