import { PieChart as PieIcon } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { displayPercent } from "../../lib/format";
import { useTeamNames } from "../../lib/teamNames";
import type { MatchStats } from "../../types/matchStats";
import { Card, CardBody, CardHeader } from "../ui/Card";

const COLORS = ["#ff7a66", "#5cc8ff"];

export function PossessionCard({ stats }: { stats: MatchStats }) {
  const names = useTeamNames();
  const a = stats.teams.team_a;
  const b = stats.teams.team_b;
  const known = a.possession_percentage !== null && b.possession_percentage !== null;
  const data = [
    { name: names.team_a, value: a.possession_percentage ?? 0, seconds: a.possession_seconds },
    { name: names.team_b, value: b.possession_percentage ?? 0, seconds: b.possession_seconds },
  ];
  const leader = known ? (data[0].value >= data[1].value ? 0 : 1) : null;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader icon={<PieIcon />} title="Possession" description="Share of time a team clearly had the ball." />
      <CardBody className="flex flex-1 flex-col">
        {known ? (
          <>
            <div className="relative mx-auto aspect-square w-full max-w-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    dataKey="value"
                    innerRadius="72%"
                    outerRadius="100%"
                    paddingAngle={3}
                    cornerRadius={6}
                    stroke="none"
                    startAngle={90}
                    endAngle={-270}
                    animationDuration={1100}
                  >
                    {data.map((_, i) => (
                      <Cell key={i} fill={COLORS[i]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
                <div>
                  <p className="font-mono text-3xl font-semibold text-white tabular">{displayPercent(data[leader!].value)}</p>
                  <p className="mt-0.5 max-w-28 truncate text-[12px] text-zinc-400">{data[leader!].name}</p>
                </div>
              </div>
            </div>
            <ul className="mt-6 space-y-2.5">
              {data.map((d, i) => (
                <li key={d.name} className="flex items-center gap-3 text-sm">
                  <span className="size-2.5 rounded-full" style={{ background: COLORS[i] }} />
                  <span className="min-w-0 flex-1 truncate text-zinc-300">{d.name}</span>
                  {d.seconds !== null && d.seconds !== undefined ? (
                    <span className="font-mono text-[12px] text-zinc-500 tabular">{d.seconds.toFixed(1)}s</span>
                  ) : null}
                  <span className="w-14 text-right font-mono font-medium text-white tabular">{displayPercent(d.value)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="my-auto text-center text-sm text-zinc-400">Not enough confirmed possession to split between teams.</p>
        )}
      </CardBody>
    </Card>
  );
}
