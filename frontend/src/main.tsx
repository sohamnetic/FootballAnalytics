import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { getToken, setToken } from "./api/client";
import "./index.css";

async function enableDemoApi() {
  if (!import.meta.env.DEV || import.meta.env.VITE_MOCK_API !== "1") return;
  const { setupWorker } = await import("msw/browser");
  const { handlers } = await import("./mocks/handlers");
  await setupWorker(...handlers).start({ onUnhandledRequest: "bypass", quiet: true });
  // Demo mode starts signed in so every page can be explored without an account.
  if (!getToken()) setToken("demo-token");
}

enableDemoApi().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
