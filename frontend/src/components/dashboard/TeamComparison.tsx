import { Swords } from "lucide-react";
import { motion } from "motion/react";
import { useTeamNames } from "../../lib/teamNames";
import type { TeamStats } from "../../types/matchStats";
import { Card, CardBody, CardHeader } from "../ui/Card";

const ROWS: [keyof TeamStats, string][] = [
  ["goals", "Goals"],
  ["shots", "Shots"],
  ["shots_on_target", "Shots on target"],
  ["completed_passes", "Completed passes"],
  ["interceptions", "Interceptions"],
  ["ball_recoveries", "Ball recoveries"],
];

export function TeamComparison({ a, b }: { a: TeamStats; b: TeamStats }) {
  const names = useTeamNames();
  return (
    <Card>
      <CardHeader icon={<Swords />} title="Head to head" description="How the two sides compare." />
      <CardBody>
        <div className="mb-4 flex justify-between text-[12px] font-medium">
          <span className="flex items-center gap-2 text-team-a">
            <span className="size-2 rounded-full bg-team-a" />
            {names.team_a}
          </span>
          <span className="flex items-center gap-2 text-team-b">
            {names.team_b}
            <span className="size-2 rounded-full bg-team-b" />
          </span>
        </div>
        <div className="space-y-5">
          {ROWS.filter(([key]) => a[key] !== null && b[key] !== null).map(([key, label], i) => {
            const va = Number(a[key] ?? 0);
            const vb = Number(b[key] ?? 0);
            const max = Math.max(va, vb, 1);
            return (
              <div key={key}>
                <div className="grid grid-cols-[3rem_1fr_3rem] items-baseline text-sm">
                  <span className={`font-mono font-semibold tabular ${va > vb ? "text-white" : "text-zinc-400"}`}>{va}</span>
                  <span className="text-center text-[13px] text-zinc-400">{label}</span>
                  <span className={`text-right font-mono font-semibold tabular ${vb > va ? "text-white" : "text-zinc-400"}`}>{vb}</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1">
                  <div className="flex h-1.5 justify-end overflow-hidden rounded-full bg-white/[0.04]">
                    <motion.span
                      className="rounded-full bg-team-a"
                      initial={{ width: 0 }}
                      whileInView={{ width: `${(va / max) * 100}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.9, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }}
                    />
                  </div>
                  <div className="flex h-1.5 overflow-hidden rounded-full bg-white/[0.04]">
                    <motion.span
                      className="rounded-full bg-team-b"
                      initial={{ width: 0 }}
                      whileInView={{ width: `${(vb / max) * 100}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.9, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {a.shots === null || b.shots === null ? (
          <p className="mt-6 text-[12px] text-zinc-500">
            Shots and goals aren't measured for this video: the goals couldn't be located in it.
          </p>
        ) : null}
        {a.pass_accuracy === null && b.pass_accuracy === null ? (
          <p className="mt-6 text-[12px] text-zinc-500">
            Pass accuracy isn't shown: we count completed passes, but can't reliably tell when a pass was attempted.
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
