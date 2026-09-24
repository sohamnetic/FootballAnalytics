import { Check } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { BrandMark } from "./BrandMark";

const POINTS = [
  "Every player tracked and identified",
  "Possession, passes, turnovers and shots",
  "Your matches, saved and ready to revisit",
];

export function AuthLayout({ title, subtitle, children, footer }: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="relative isolate grid min-h-dvh lg:grid-cols-2">
      <div aria-hidden="true" className="app-backdrop pointer-events-none fixed inset-0 -z-10" />

      <div className="flex flex-col px-6 py-8 sm:px-12">
        <BrandMark />
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto my-auto w-full max-w-sm py-12"
        >
          <h1 className="text-3xl font-semibold tracking-tight text-white">{title}</h1>
          <p className="mt-2 text-[15px] text-zinc-400">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <div className="mt-8 text-center text-sm text-zinc-400">{footer}</div>
        </motion.div>
      </div>

      <div className="relative hidden overflow-hidden border-l border-white/[0.06] bg-ink-900 lg:block">
        <svg aria-hidden="true" className="absolute inset-0 h-full w-full opacity-[0.12]" preserveAspectRatio="xMidYMid slice" viewBox="0 0 400 600">
          <g fill="none" stroke="#7eecc0" strokeWidth="1.5">
            <rect x="30" y="30" width="340" height="540" rx="6" />
            <line x1="30" y1="300" x2="370" y2="300" />
            <circle cx="200" cy="300" r="55" />
            <rect x="120" y="30" width="160" height="80" />
            <rect x="120" y="490" width="160" height="80" />
          </g>
        </svg>
        <div aria-hidden="true" className="absolute top-1/4 left-1/2 size-96 -translate-x-1/2 rounded-full bg-pitch-400/15 blur-3xl" />
        <div className="relative flex h-full flex-col justify-end p-14">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="glass max-w-md rounded-3xl bg-ink-850/70 p-8"
          >
            <p className="text-2xl leading-snug font-semibold tracking-tight text-white">
              Your match, <span className="text-gradient">in numbers.</span>
            </p>
            <ul className="mt-6 space-y-3">
              {POINTS.map((p) => (
                <li key={p} className="flex items-center gap-3 text-sm text-zinc-300">
                  <span className="grid size-5 place-items-center rounded-full bg-pitch-400/15 text-pitch-300 [&_svg]:size-3">
                    <Check />
                  </span>
                  {p}
                </li>
              ))}
            </ul>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
