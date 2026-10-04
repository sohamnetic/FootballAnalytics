import { Download, Share, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useInstall } from "../../lib/install";
import { Button } from "../ui/Button";

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
  if (hidden || !(install.canPrompt || install.iosHint)) return null;

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
        <p className="text-[12px] leading-snug text-zinc-400">
          {install.canPrompt ? (
            "Open it from your home screen like an app."
          ) : (
            <>
              Tap <Share className="inline size-3.5 align-[-2px]" /> Share, then "Add to Home Screen".
            </>
          )}
        </p>
      </div>
      {install.canPrompt ? (
        <Button
          size="sm"
          onClick={async () => {
            if (await install.install()) toast.success("Added to your home screen");
          }}
        >
          <Download /> Install
        </Button>
      ) : null}
      <Button variant="ghost" size="icon" aria-label="Dismiss" onClick={dismiss} className="size-8">
        <X />
      </Button>
    </div>
  );
}
