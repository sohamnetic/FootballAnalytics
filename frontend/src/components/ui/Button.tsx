import { Slot } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";
import { Spinner } from "./Spinner";

const variants = {
  primary:
    "bg-linear-to-b from-pitch-300 to-pitch-500 text-ink-950 shadow-glow hover:from-pitch-200 hover:to-pitch-400",
  secondary: "glass text-zinc-100 hover:bg-white/[0.07] hover:border-white/15",
  ghost: "text-zinc-300 hover:bg-white/[0.06] hover:text-white",
  danger: "bg-rose-500/10 text-rose-300 ring-1 ring-inset ring-rose-400/25 hover:bg-rose-500/20",
  gold: "bg-linear-to-b from-gold-300 to-gold-500 text-ink-950 hover:from-gold-300 hover:to-gold-400",
} as const;

const sizes = {
  sm: "h-8 gap-1.5 rounded-lg px-3 text-[13px]",
  md: "h-10 gap-2 rounded-xl px-4 text-sm",
  lg: "h-12 gap-2.5 rounded-xl px-6 text-[15px]",
  icon: "size-9 rounded-lg",
} as const;

type ButtonProps = ComponentProps<"button"> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
  asChild?: boolean;
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  asChild = false,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center justify-center font-medium whitespace-nowrap transition-all duration-200 select-none active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={asChild ? undefined : disabled || loading}
      {...props}
    >
      {asChild ? (
        children
      ) : (
        <>
          {loading ? <Spinner /> : null}
          {children}
        </>
      )}
    </Comp>
  );
}
