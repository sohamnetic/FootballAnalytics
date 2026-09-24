import { Eye, EyeOff, Lock } from "lucide-react";
import { useId, useState, type ComponentProps, type ReactNode } from "react";
import { cn } from "../../lib/cn";

const inputBase =
  "h-11 w-full rounded-xl border border-white/[0.08] bg-ink-900/70 px-3.5 text-[14px] text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.03)] transition-colors outline-none placeholder:text-zinc-500 hover:border-white/15 focus:border-pitch-400/60 focus:ring-4 focus:ring-pitch-400/10 disabled:opacity-60 read-only:text-zinc-400";

type FieldProps = ComponentProps<"input"> & {
  label: string;
  icon?: ReactNode;
  hint?: ReactNode;
  trailing?: ReactNode;
};

export function Field({ label, icon, hint, trailing, className, id, ...props }: FieldProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={inputId} className="block text-[13px] font-medium text-zinc-300">
        {label}
      </label>
      <div className="relative">
        {icon ? (
          <span className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-zinc-500 [&_svg]:size-4">
            {icon}
          </span>
        ) : null}
        <input id={inputId} className={cn(inputBase, icon && "pl-10", trailing && "pr-12")} {...props} />
        {trailing ? <span className="absolute top-1/2 right-1.5 -translate-y-1/2">{trailing}</span> : null}
      </div>
      {hint ? <p className="text-[12px] text-zinc-500">{hint}</p> : null}
    </div>
  );
}

export function PasswordField(props: Omit<FieldProps, "type" | "icon" | "trailing" | "label"> & { label?: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <Field
      label={props.label ?? "Password"}
      type={visible ? "text" : "password"}
      icon={<Lock />}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="grid size-8 cursor-pointer place-items-center rounded-lg text-zinc-400 transition-colors hover:bg-white/[0.06] hover:text-white [&_svg]:size-4"
        >
          {visible ? <EyeOff /> : <Eye />}
        </button>
      }
      {...props}
    />
  );
}
