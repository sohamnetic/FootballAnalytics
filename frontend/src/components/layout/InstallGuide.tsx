import { Dialog } from "radix-ui";
import {
  Check,
  Download,
  EllipsisVertical,
  Home,
  Menu,
  MonitorDown,
  Share,
  SquarePlus,
  X,
  type LucideIcon,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { detectBrowser, useInstall, type Browser } from "../../lib/install";
import { Button } from "../ui/Button";

type Step = { icon: LucideIcon; text: ReactNode };

const b = (s: string) => <strong className="font-semibold text-white">{s}</strong>;

const STEPS: Record<Browser, { title: string; steps: Step[]; note?: string }> = {
  "ios-safari": {
    title: "iPhone / iPad (Safari)",
    steps: [
      { icon: Share, text: <>Tap the {b("Share")} button: the square with an arrow, at the bottom of Safari (top on iPad).</> },
      { icon: SquarePlus, text: <>Scroll down the list and tap {b("Add to Home Screen")}.</> },
      { icon: Check, text: <>Tap {b("Add")} in the top right corner.</> },
      { icon: Home, text: <>Open {b("TactiVision")} from your home screen. It opens full screen like an app.</> },
    ],
  },
  "ios-other": {
    title: "iPhone / iPad",
    steps: [
      { icon: Share, text: <>Tap {b("Share")}: in Chrome it's next to the address bar, in other browsers it's in the menu.</> },
      { icon: SquarePlus, text: <>Tap {b("Add to Home Screen")}.</> },
      { icon: Check, text: <>Tap {b("Add")}.</> },
      { icon: Home, text: <>Open {b("TactiVision")} from your home screen.</> },
    ],
    note: "Don't see Add to Home Screen? Open this page in Safari and follow the same steps.",
  },
  "android-chrome": {
    title: "Android (Chrome)",
    steps: [
      { icon: EllipsisVertical, text: <>Tap the {b("⋮")} menu at the top right of Chrome.</> },
      { icon: Download, text: <>Tap {b("Install app")} (on some phones it says {b("Add to Home screen")}).</> },
      { icon: Check, text: <>Tap {b("Install")} to confirm.</> },
      { icon: Home, text: <>Open {b("TactiVision")} from your home screen or app drawer.</> },
    ],
  },
  "android-samsung": {
    title: "Samsung Internet",
    steps: [
      { icon: Menu, text: <>Tap the {b("≡")} menu at the bottom right.</> },
      { icon: SquarePlus, text: <>Tap {b("Add page to")}, then {b("Home screen")}.</> },
      { icon: Check, text: <>Tap {b("Add")}.</> },
      { icon: Home, text: <>Open {b("TactiVision")} from your home screen.</> },
    ],
  },
  "android-firefox": {
    title: "Android (Firefox)",
    steps: [
      { icon: EllipsisVertical, text: <>Tap the {b("⋮")} menu.</> },
      { icon: Download, text: <>Tap {b("Install")} or {b("Add to Home screen")}.</> },
      { icon: Check, text: <>Confirm with {b("Add")}.</> },
      { icon: Home, text: <>Open {b("TactiVision")} from your home screen.</> },
    ],
  },
  "desktop-chromium": {
    title: "Computer (Chrome or Edge)",
    steps: [
      { icon: MonitorDown, text: <>Click the {b("install icon")} at the right end of the address bar.</> },
      { icon: Download, text: <>Or open the browser menu and choose {b("Install TactiVision")} (Chrome: Cast, save and share).</> },
      { icon: Check, text: <>Click {b("Install")}. TactiVision opens in its own window.</> },
    ],
  },
  other: {
    title: "Your browser",
    steps: [
      { icon: Menu, text: <>Open the browser menu.</> },
      { icon: SquarePlus, text: <>Look for {b("Install app")} or {b("Add to Home screen")}.</> },
      { icon: Check, text: <>Confirm, then open {b("TactiVision")} from your home screen.</> },
    ],
    note: "If your browser has no install option, use Chrome (Android, computer) or Safari (iPhone).",
  },
};

/** Opens the install steps for this phone/browser. When the browser offers
 * one-tap install (Chrome on Android, Edge/Chrome on a computer) there is
 * also an "Install now" button. */
export function InstallGuide({ trigger }: { trigger: ReactNode }) {
  const install = useInstall();
  const [open, setOpen] = useState(false);
  const guide = STEPS[detectBrowser()];

  async function installNow() {
    if (await install.install()) {
      setOpen(false);
      toast.success("TactiVision added to your home screen");
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-[60] max-h-[90dvh] overflow-y-auto rounded-t-3xl border-t border-white/[0.08] bg-ink-900 px-5 pt-3 pb-[calc(1.5rem+env(safe-area-inset-bottom))] md:inset-x-auto md:top-1/2 md:bottom-auto md:left-1/2 md:w-[calc(100vw-2rem)] md:max-w-md md:-translate-x-1/2 md:-translate-y-1/2 md:rounded-2xl md:border md:p-6">
          <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-white/15 md:hidden" />
          <div className="flex items-center gap-3 pr-10">
            <img src="/icons/icon-192.png" alt="" className="size-12 rounded-xl" />
            <div className="min-w-0">
              <Dialog.Title className="font-semibold text-white">Install TactiVision</Dialog.Title>
              <Dialog.Description className="text-[13px] text-zinc-400">{guide.title}</Dialog.Description>
            </div>
          </div>
          <Dialog.Close asChild>
            <Button variant="ghost" size="icon" aria-label="Close" className="absolute top-5 right-4 md:top-4">
              <X />
            </Button>
          </Dialog.Close>

          {install.standalone ? (
            <p className="mt-5 rounded-xl bg-pitch-400/10 px-4 py-3 text-sm text-pitch-200">
              You're already using the installed app.
            </p>
          ) : (
            <>
              {install.canPrompt ? (
                <div className="mt-5 rounded-xl bg-pitch-400/[0.07] p-4 ring-1 ring-pitch-400/20">
                  <p className="text-sm text-zinc-200">Your browser can install it in one tap.</p>
                  <Button className="mt-3 w-full" onClick={installNow}>
                    <Download /> Install now
                  </Button>
                  <p className="mt-3 text-center text-[12px] text-zinc-500">Or do it yourself:</p>
                </div>
              ) : null}

              <ol className="mt-5 space-y-3">
                {guide.steps.map((step, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white/[0.06] font-mono text-[13px] font-semibold text-pitch-300">
                      {i + 1}
                    </span>
                    <div className="flex min-w-0 flex-1 items-start gap-2.5 pt-1">
                      <step.icon className="mt-0.5 size-4 shrink-0 text-zinc-400" />
                      <p className="text-sm leading-relaxed text-zinc-300">{step.text}</p>
                    </div>
                  </li>
                ))}
              </ol>
              {guide.note ? <p className="mt-4 text-[12px] leading-relaxed text-zinc-500">{guide.note}</p> : null}
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
