import { AlertTriangle, CircleAlert, Info } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

const tones = {
  error: { cls: "border-rose-400/25 bg-rose-500/[0.08] text-rose-200", icon: <CircleAlert /> },
  info: { cls: "border-sky-400/20 bg-sky-400/[0.06] text-sky-100", icon: <Info /> },
  warning: { cls: "border-gold-400/25 bg-gold-400/[0.07] text-gold-300", icon: <AlertTriangle /> },
} as const;

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: keyof typeof tones;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const t = tones[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-xl border px-4 py-3 text-[13px] leading-relaxed", t.cls, className)}
    >
      <span className="mt-0.5 shrink-0 [&_svg]:size-4">{t.icon}</span>
      <div className="min-w-0">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className={cn(title && "mt-0.5 opacity-85")}>{children}</div> : null}
      </div>
    </div>
  );
}
