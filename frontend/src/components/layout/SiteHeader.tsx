import { Dialog, DropdownMenu } from "radix-ui";
import { FolderOpen, LogOut, Menu, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { cn } from "../../lib/cn";
import { Button } from "../ui/Button";
import { BrandMark } from "./BrandMark";

function initials(name: string) {
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "U";
}

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-lg px-3 py-1.5 text-sm transition-colors",
    isActive ? "bg-white/[0.07] text-white" : "text-zinc-400 hover:text-white",
  );

export function SiteHeader() {
  const { user, ready, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  function signOut() {
    logout();
    navigate("/");
  }

  const displayName = user ? user.name || user.email : "";

  return (
    <header
      className={cn(
        "sticky top-0 z-40 transition-all duration-300",
        scrolled ? "border-b border-white/[0.06] bg-ink-950/75 backdrop-blur-xl" : "border-b border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <BrandMark />

        <nav className="hidden items-center gap-2 md:flex" aria-label="Main">
          {ready && user ? (
            <>
              <NavLink to="/matches" className={navLinkClass}>
                Matches
              </NavLink>
              <Button asChild size="sm" className="ml-1">
                <Link to="/upload">
                  <Plus /> New analysis
                </Link>
              </Button>
              <DropdownMenu.Root>
                <DropdownMenu.Trigger
                  aria-label="Account menu"
                  className="ml-2 grid size-9 cursor-pointer place-items-center rounded-full bg-linear-to-br from-gold-300 to-gold-500 text-[13px] font-semibold text-ink-950 ring-2 ring-white/10 transition hover:ring-pitch-400/50"
                >
                  {initials(displayName)}
                </DropdownMenu.Trigger>
                <DropdownMenu.Portal>
                  <DropdownMenu.Content
                    align="end"
                    sideOffset={10}
                    className="glass z-50 min-w-56 rounded-xl bg-ink-900/95 p-1.5 text-sm"
                  >
                    <div className="px-2.5 py-2">
                      <p className="truncate font-medium text-white">{user.name || "Your account"}</p>
                      <p className="truncate text-[12px] text-zinc-400">{user.email}</p>
                    </div>
                    <DropdownMenu.Separator className="my-1 h-px bg-white/[0.07]" />
                    <DropdownMenu.Item
                      onSelect={() => navigate("/matches")}
                      className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-zinc-300 outline-none data-[highlighted]:bg-white/[0.07] data-[highlighted]:text-white [&_svg]:size-4"
                    >
                      <FolderOpen /> My matches
                    </DropdownMenu.Item>
                    <DropdownMenu.Item
                      onSelect={signOut}
                      className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-zinc-300 outline-none data-[highlighted]:bg-white/[0.07] data-[highlighted]:text-white [&_svg]:size-4"
                    >
                      <LogOut /> Log out
                    </DropdownMenu.Item>
                  </DropdownMenu.Content>
                </DropdownMenu.Portal>
              </DropdownMenu.Root>
            </>
          ) : ready ? (
            <>
              <NavLink to="/login" className={navLinkClass}>
                Sign in
              </NavLink>
              <Button asChild size="sm">
                <Link to="/signup">Get started</Link>
              </Button>
            </>
          ) : null}
        </nav>

        <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
          <Dialog.Trigger asChild>
            <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
              <Menu />
            </Button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm md:hidden" />
            <Dialog.Content className="fixed inset-x-3 top-3 z-50 rounded-2xl border border-white/[0.08] bg-ink-900/95 p-4 backdrop-blur-xl md:hidden">
              <div className="flex items-center justify-between">
                <Dialog.Title className="text-sm font-medium text-zinc-400">Menu</Dialog.Title>
                <Dialog.Close asChild>
                  <Button variant="ghost" size="icon" aria-label="Close menu">
                    <X />
                  </Button>
                </Dialog.Close>
              </div>
              <Dialog.Description className="sr-only">Site navigation</Dialog.Description>
              <div className="mt-3 flex flex-col gap-1">
                {user ? (
                  <>
                    <p className="px-3 pb-2 text-[13px] text-zinc-500">Signed in as {displayName}</p>
                    <NavLink to="/matches" className={navLinkClass}>
                      My matches
                    </NavLink>
                    <NavLink to="/upload" className={navLinkClass}>
                      New analysis
                    </NavLink>
                    <button
                      type="button"
                      onClick={signOut}
                      className="cursor-pointer rounded-lg px-3 py-1.5 text-left text-sm text-zinc-400 hover:text-white"
                    >
                      Log out
                    </button>
                  </>
                ) : (
                  <>
                    <NavLink to="/login" className={navLinkClass}>
                      Sign in
                    </NavLink>
                    <Button asChild className="mt-2">
                      <Link to="/signup">Get started</Link>
                    </Button>
                  </>
                )}
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    </header>
  );
}
