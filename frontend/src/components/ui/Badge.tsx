import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";

const tones = {
  neutral: "bg-white/[0.06] text-zinc-300 ring-white/10",
  pitch: "bg-pitch-400/10 text-pitch-300 ring-pitch-400/25",
  gold: "bg-gold-400/10 text-gold-300 ring-gold-400/25",
  danger: "bg-rose-500/10 text-rose-300 ring-rose-400/25",
  info: "bg-sky-400/10 text-sky-300 ring-sky-400/25",
} as const;

export function Badge({
  tone = "neutral",
  dot = false,
  pulse = false,
  className,
  children,
  ...props
}: ComponentProps<"span"> & { tone?: keyof typeof tones; dot?: boolean; pulse?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] leading-none font-medium ring-1 ring-inset [&_svg]:size-3.5",
        tones[tone],
        className,
      )}
      {...props}
    >
      {dot ? (
        <span className={cn("size-1.5 rounded-full bg-current", pulse && "animate-pulse-soft")} aria-hidden="true" />
      ) : null}
      {children}
    </span>
  );
}
