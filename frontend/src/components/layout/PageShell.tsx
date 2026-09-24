import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

export function PageShell({
  children,
  width = "wide",
  footer = true,
  className,
}: {
  children: ReactNode;
  width?: "wide" | "narrow" | "full";
  footer?: boolean;
  className?: string;
}) {
  return (
    <div className="relative isolate flex min-h-dvh flex-col overflow-x-clip">
      <div aria-hidden="true" className="app-backdrop pointer-events-none fixed inset-0 -z-10" />
      <div aria-hidden="true" className="grid-lines pointer-events-none absolute inset-x-0 top-0 -z-10 h-[40rem]" />
      <SiteHeader />
      <motion.main
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className={cn(
          "mx-auto w-full flex-1 px-4 sm:px-6 lg:px-8",
          width === "wide" && "max-w-7xl",
          width === "narrow" && "max-w-2xl",
          className,
        )}
      >
        {children}
      </motion.main>
      {footer ? <SiteFooter /> : null}
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 pt-10 pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="mb-2 text-[12px] font-medium tracking-[0.18em] text-pitch-400 uppercase">{eyebrow}</p>
        ) : null}
        <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-zinc-400">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function FullPageStatus({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-ink-950 text-sm text-zinc-400">
      <div className="flex items-center gap-3">
        <span className="size-2 animate-pulse-soft rounded-full bg-pitch-400" />
        {children}
      </div>
    </div>
  );
}
