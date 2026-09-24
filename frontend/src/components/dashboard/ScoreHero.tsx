import { Clock, Film, Gauge } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";
import { displayPercent, videoLabel } from "../../lib/format";
import { useTeamNames } from "../../lib/teamNames";
import type { MatchStats } from "../../types/matchStats";

function windowLabel(start: number | null, duration: number | null) {
  if (duration === null || duration === undefined) return "Full match";
  const from = start ?? 0;
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
  return `${fmt(from)} – ${fmt(from + duration)}`;
}

export function ScoreHero({ stats }: { stats: MatchStats }) {
  const names = useTeamNames();
  const a = stats.teams.team_a;
  const b = stats.teams.team_b;
  const possA = a.possession_percentage;
  const possB = b.possession_percentage;
  const hasPoss = possA !== null && possB !== null;
  const goalsKnown = a.goals !== null && b.goals !== null;

  return (
    <section className="glass relative overflow-hidden rounded-3xl" aria-label="Scoreboard">
      <div aria-hidden="true" className="absolute -top-24 -left-24 size-72 rounded-full bg-team-a/15 blur-3xl" />
      <div aria-hidden="true" className="absolute -top-24 -right-24 size-72 rounded-full bg-team-b/15 blur-3xl" />

      <div className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-4 px-5 pt-10 pb-8 sm:px-10">
        <TeamName name={names.team_a} side="Home" color="bg-team-a" align="left" />
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="text-center"
        >
          <p className={`font-mono text-5xl font-semibold tracking-tight tabular sm:text-7xl ${goalsKnown ? "text-white" : "text-zinc-600"}`}>
            {a.goals ?? "–"}
            <span className="mx-2 text-zinc-600 sm:mx-4">:</span>
            {b.goals ?? "–"}
          </p>
          <p className="mt-2 text-[12px] tracking-[0.16em] text-zinc-500 uppercase">
            {goalsKnown ? "Goals" : "Goals not measured"}
          </p>
        </motion.div>
        <TeamName name={names.team_b} side="Away" color="bg-team-b" align="right" />
      </div>

      {hasPoss ? (
        <div className="relative px-5 pb-6 sm:px-10">
          <div className="flex justify-between font-mono text-[13px] tabular">
            <span className="text-team-a">{displayPercent(possA)}</span>
            <span className="text-[11px] tracking-[0.16em] text-zinc-500 uppercase">Possession</span>
            <span className="text-team-b">{displayPercent(possB)}</span>
          </div>
          <div className="mt-2 flex h-2 gap-1 overflow-hidden rounded-full">
            <motion.span
              className="rounded-full bg-team-a"
              initial={{ width: "50%" }}
              animate={{ width: `${possA}%` }}
              transition={{ duration: 1.1, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            />
            <span className="flex-1 rounded-full bg-team-b" />
          </div>
        </div>
      ) : null}

      <div className="relative flex flex-wrap gap-x-6 gap-y-2 border-t border-white/[0.06] px-5 py-4 text-[13px] text-zinc-400 sm:px-10">
        <Meta icon={<Clock />} label={windowLabel(stats.match.start_time_s, stats.match.duration_s)} />
        <Meta icon={<Gauge />} label={`${Math.round(stats.match.fps)} fps`} />
        <Meta icon={<Film />} label={videoLabel(stats.match.video)} />
      </div>
    </section>
  );
}

function TeamName({ name, side, color, align }: { name: string; side: string; color: string; align: "left" | "right" }) {
  return (
    <div className={align === "right" ? "text-right" : ""}>
      <div className={`flex items-center gap-2 text-[11px] font-medium tracking-[0.16em] text-zinc-500 uppercase ${align === "right" ? "justify-end" : ""}`}>
        <span className={`size-2 rounded-full ${color}`} />
        {side}
      </div>
      <p className="mt-2 text-xl font-semibold tracking-tight break-words text-white sm:text-3xl">{name}</p>
    </div>
  );
}

function Meta({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <span className="flex min-w-0 items-center gap-2 [&_svg]:size-4 [&_svg]:text-zinc-500">
      {icon}
      <span className="truncate">{label}</span>
    </span>
  );
}
