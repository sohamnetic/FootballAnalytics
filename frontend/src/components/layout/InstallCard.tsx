import { Download, X } from "lucide-react";
import { useState } from "react";
import { useInstall } from "../../lib/install";
import { Button } from "../ui/Button";
import { InstallGuide } from "./InstallGuide";

const DISMISSED_KEY = "fa_install_dismissed";

function wasDismissed() {
  try {
    return localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

// "Add to home screen" nudge on phones; hidden once installed or dismissed
export function InstallCard() {
  const install = useInstall();
  const [hidden, setHidden] = useState(wasDismissed);
  if (hidden || install.standalone) return null;

  function dismiss() {
    setHidden(true);
    try {
      localStorage.setItem(DISMISSED_KEY, "1");
    } catch {
      /* private mode */
    }
  }

  return (
    <div className="glass mb-6 flex items-center gap-3 rounded-2xl p-4 md:hidden">
      <img src="/icons/icon-192.png" alt="" className="size-11 shrink-0 rounded-xl" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-white">Install TactiVision</p>
        <p className="text-[12px] leading-snug text-zinc-400">Open it from your home screen like an app.</p>
      </div>
      <InstallGuide
        trigger={
          <Button size="sm">
            <Download /> Install
          </Button>
        }
      />
      <Button variant="ghost" size="icon" aria-label="Dismiss" onClick={dismiss} className="size-8">
        <X />
      </Button>
    </div>
  );
}
