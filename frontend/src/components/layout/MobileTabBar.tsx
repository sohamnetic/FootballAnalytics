import { Dialog } from "radix-ui";
import { Download, FolderOpen, LogOut, Plus, User } from "lucide-react";
import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { cn } from "../../lib/cn";
import { useInstall } from "../../lib/install";
import { Button } from "../ui/Button";
import { InstallGuide } from "./InstallGuide";
import { initials } from "./SiteHeader";

const tab = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex flex-1 flex-col items-center justify-center gap-1 py-2 text-[11px] font-medium transition-colors [&_svg]:size-5",
    isActive ? "text-pitch-300" : "text-zinc-500 active:text-zinc-300",
  );

// Phone navigation, like a native app. Only for signed-in users and only
// below the md breakpoint; the header nav takes over on wider screens.
export function MobileTabBar() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <nav
      aria-label="App"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/[0.07] bg-ink-950/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
    >
      <div className="mx-auto flex h-16 max-w-md items-stretch">
        <NavLink to="/matches" className={tab}>
          <FolderOpen /> Matches
        </NavLink>
        <NavLink to="/upload" className="flex flex-1 items-center justify-center" aria-label="New analysis">
          {({ isActive }) => (
            <span
              className={cn(
                "grid size-12 place-items-center rounded-2xl bg-linear-to-b from-pitch-300 to-pitch-500 text-ink-950 shadow-glow transition-transform active:scale-95 [&_svg]:size-6",
                isActive && "ring-2 ring-pitch-200/60",
              )}
            >
              <Plus />
            </span>
          )}
        </NavLink>
        <AccountTab />
      </div>
    </nav>
  );
}

function AccountTab() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const install = useInstall();
  const name = user ? user.name || user.email : "";

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger className={tab({ isActive: open })}>
        <span className="grid size-6 place-items-center rounded-full bg-linear-to-br from-gold-300 to-gold-500 text-[10px] font-semibold text-ink-950">
          {initials(name)}
        </span>
        Account
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 rounded-t-3xl border-t border-white/[0.08] bg-ink-900 px-5 pt-3 pb-[calc(1.25rem+env(safe-area-inset-bottom))]">
          <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-white/15" />
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-full bg-linear-to-br from-gold-300 to-gold-500 text-sm font-semibold text-ink-950">
              {initials(name)}
            </span>
            <div className="min-w-0">
              <Dialog.Title className="truncate font-medium text-white">{user?.name || "Your account"}</Dialog.Title>
              <Dialog.Description className="truncate text-[13px] text-zinc-400">{user?.email}</Dialog.Description>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-2">
            {!install.standalone ? (
              <InstallGuide
                trigger={
                  <Button variant="secondary" className="justify-start">
                    <Download /> Install app
                  </Button>
                }
              />
            ) : null}
            <Button
              variant="secondary"
              className="justify-start"
              onClick={() => {
                setOpen(false);
                navigate("/matches");
              }}
            >
              <User /> My matches
            </Button>
            <Button
              variant="danger"
              className="justify-start"
              onClick={() => {
                setOpen(false);
                logout();
                navigate("/");
              }}
            >
              <LogOut /> Log out
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
