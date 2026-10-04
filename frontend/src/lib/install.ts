import { useEffect, useState } from "react";

// Chrome/Android fire beforeinstallprompt once, often before React starts,
// so catch it as soon as this module loads (main.tsx imports it).
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let deferred: InstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((fn) => fn());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e as InstallPromptEvent;
    notify();
  });
  window.addEventListener("appinstalled", () => {
    deferred = null;
    notify();
  });
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

export type Browser =
  | "ios-safari"
  | "ios-other"
  | "android-chrome"
  | "android-samsung"
  | "android-firefox"
  | "desktop-chromium"
  | "other";

/** Which install steps to show. */
export function detectBrowser(): Browser {
  if (typeof navigator === "undefined") return "other";
  const ua = navigator.userAgent;
  if (isIOS()) return /CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua) ? "ios-other" : "ios-safari";
  if (/Android/i.test(ua)) {
    if (/SamsungBrowser/i.test(ua)) return "android-samsung";
    if (/Firefox/i.test(ua)) return "android-firefox";
    return "android-chrome";
  }
  if (/Edg\/|Chrome\//.test(ua) && !/OPR\//.test(ua)) return "desktop-chromium";
  return "other";
}

/** canPrompt: the browser can show its own install dialog (Chrome/Edge).
 * Elsewhere (iPhone, Samsung...) InstallGuide explains the manual steps. */
export function useInstall() {
  const [, setTick] = useState(0);
  useEffect(() => {
    const fn = () => setTick((t) => t + 1);
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  }, []);
  const standalone = isStandalone();
  return {
    standalone,
    canPrompt: !standalone && deferred !== null,
    async install() {
      if (!deferred) return false;
      await deferred.prompt();
      const { outcome } = await deferred.userChoice;
      deferred = null;
      notify();
      return outcome === "accepted";
    },
  };
}
