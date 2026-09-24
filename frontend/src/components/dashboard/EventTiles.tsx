import { ArrowRightLeft, Crosshair, Goal, RotateCcw, ShieldHalf, Target, Timer } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import type { EventSummary } from "../../types/matchStats";

export function EventTiles({ summary }: { summary: EventSummary }) {
  const tiles: [ReactNode, string, number | null][] = [
    [<Goal />, "Goals", summary.goals],
    [<Target />, "Shots", summary.shots],
    [<Crosshair />, "On target", summary.shots_on_target],
    [<ArrowRightLeft />, "Completed passes", summary.completed_passes],
    [<ShieldHalf />, "Interceptions", summary.interceptions],
    [<RotateCcw />, "Recoveries", summary.recoveries],
    [<Timer />, "Possession spells", summary.possession_intervals],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {tiles.map(([icon, label, value], i) => (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.05, duration: 0.5 }}
          className="glass rounded-2xl p-4"
        >
          <div className="text-zinc-500 [&_svg]:size-4">{icon}</div>
          <p className={`mt-4 font-mono text-3xl font-semibold tabular ${value === null ? "text-zinc-600" : "text-white"}`}>
            {value ?? "–"}
          </p>
          <p className="mt-1 text-[12px] text-zinc-400">{label}</p>
          {value === null ? <p className="text-[11px] text-zinc-600">Not measured</p> : null}
        </motion.div>
      ))}
    </div>
  );
}
