import { Check } from "lucide-react";
import { Fragment } from "react";
import { cn } from "../../lib/cn";

const STEPS = ["Upload", "Set up", "Analyze"];

export function FlowSteps({ current }: { current: 0 | 1 | 2 }) {
  return (
    <ol className="flex items-center gap-3 pt-8 text-[13px]" aria-label="Progress">
      {STEPS.map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <Fragment key={label}>
            {i > 0 ? (
              <li aria-hidden="true" className={cn("h-px w-8 sm:w-14", done || active ? "bg-pitch-400/50" : "bg-white/10")} />
            ) : null}
            <li className="flex items-center gap-2" aria-current={active ? "step" : undefined}>
              <span
                className={cn(
                  "grid size-6 place-items-center rounded-full font-mono text-[11px] font-semibold transition-colors [&_svg]:size-3.5",
                  done && "bg-pitch-400 text-ink-950",
                  active && "bg-pitch-400/15 text-pitch-300 ring-1 ring-pitch-400/50",
                  !done && !active && "bg-white/[0.05] text-zinc-500 ring-1 ring-white/10",
                )}
              >
                {done ? <Check /> : i + 1}
              </span>
              <span className={cn(active ? "text-white" : done ? "text-zinc-300" : "text-zinc-500")}>{label}</span>
            </li>
          </Fragment>
        );
      })}
    </ol>
  );
}
