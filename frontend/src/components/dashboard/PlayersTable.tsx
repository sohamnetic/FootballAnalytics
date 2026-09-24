import { ArrowDown, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "../../lib/cn";
import { displayPercent } from "../../lib/format";
import { teamLabel, useTeamNames } from "../../lib/teamNames";
import type { PlayerStats } from "../../types/matchStats";
import { Card, CardHeader } from "../ui/Card";

type Filter = "all" | "team_a" | "team_b";
type Col = { key: keyof PlayerStats; label: string; kind?: "percent" };

const COLS: Col[] = [
  { key: "goals", label: "Goals" },
  { key: "shots", label: "Shots" },
  { key: "shots_on_target", label: "On target" },
  { key: "shot_accuracy", label: "Shot acc.", kind: "percent" },
  { key: "successful_passes", label: "Passes" },
  { key: "interceptions", label: "Intercepts" },
  { key: "ball_recoveries", label: "Recoveries" },
];

export function PlayersTable({ players }: { players: PlayerStats[] }) {
  const names = useTeamNames();
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<keyof PlayerStats>("ball_possession_time_seconds");

  const onTeam = useMemo(() => players.filter((p) => p.team_id === "team_a" || p.team_id === "team_b"), [players]);
  const maxPoss = Math.max(...onTeam.map((p) => p.ball_possession_time_seconds), 0.001);

  const rows = useMemo(
    () =>
      onTeam
        .filter((p) => filter === "all" || p.team_id === filter)
        .sort((x, y) => Number(y[sort] ?? -1) - Number(x[sort] ?? -1)),
    [onTeam, filter, sort],
  );

  const header = (key: keyof PlayerStats, label: string, align: "left" | "right" = "right") => (
    <th key={key} scope="col" className={cn("px-3 py-3 font-medium whitespace-nowrap", align === "right" ? "text-right" : "text-left")}>
      <button
        type="button"
        onClick={() => setSort(key)}
        className={cn(
          "inline-flex cursor-pointer items-center gap-1 transition-colors hover:text-white",
          sort === key ? "text-pitch-300" : "text-zinc-500",
        )}
      >
        {label}
        <ArrowDown className={cn("size-3 transition-opacity", sort === key ? "opacity-100" : "opacity-0")} />
      </button>
    </th>
  );

  return (
    <Card>
      <CardHeader
        icon={<Users />}
        title="Players"
        description={`${onTeam.length} players identified. Click a column to sort.`}
        action={
          <div className="flex rounded-lg bg-white/[0.05] p-0.5 text-[12px]" role="group" aria-label="Filter by team">
            {(["all", "team_a", "team_b"] as Filter[]).map((id) => (
              <button
                key={id}
                type="button"
                aria-pressed={filter === id}
                onClick={() => setFilter(id)}
                className={cn(
                  "max-w-28 cursor-pointer truncate rounded-md px-3 py-1.5 transition-colors",
                  filter === id ? "bg-white/10 text-white" : "text-zinc-400 hover:text-white",
                )}
              >
                {id === "all" ? "All" : teamLabel(id, names)}
              </button>
            ))}
          </div>
        }
      />
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="border-y border-white/[0.06] bg-white/[0.02] text-[12px]">
            <tr>
              <th scope="col" className="px-5 py-3 text-left font-medium text-zinc-500 sm:px-6">
                Player
              </th>
              {header("ball_possession_time_seconds", "Possession", "left")}
              {COLS.map((c) => header(c.key, c.label))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04]">
            {rows.map((p) => {
              const a = p.team_id === "team_a";
              return (
                <tr key={p.stable_id} className="transition-colors hover:bg-white/[0.03]">
                  <td className="px-5 py-3 sm:px-6">
                    <div className="flex items-center gap-3">
                      <span
                        className={cn(
                          "grid size-8 place-items-center rounded-full font-mono text-[12px] font-semibold ring-1",
                          a ? "bg-team-a/15 text-team-a ring-team-a/30" : "bg-team-b/15 text-team-b ring-team-b/30",
                        )}
                      >
                        {p.stable_id}
                      </span>
                      <div className="min-w-0">
                        <p className="font-medium text-white">Player {p.stable_id}</p>
                        <p className="max-w-36 truncate text-[12px] text-zinc-500">{teamLabel(p.team_id, names)}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-3">
                      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-white/[0.05]">
                        <div
                          className={cn("h-full rounded-full", a ? "bg-team-a" : "bg-team-b")}
                          style={{ width: `${(p.ball_possession_time_seconds / maxPoss) * 100}%` }}
                        />
                      </div>
                      <span className="font-mono text-[13px] text-zinc-300 tabular">{p.ball_possession_time_seconds.toFixed(1)}s</span>
                    </div>
                  </td>
                  {COLS.map((c) => {
                    const v = p[c.key];
                    const empty = v === null || v === undefined;
                    const zero = v === 0;
                    return (
                      <td
                        key={c.key}
                        className={cn(
                          "px-3 py-3 text-right font-mono text-[13px] tabular",
                          empty || zero ? "text-zinc-600" : "text-white",
                        )}
                      >
                        {empty ? "–" : c.kind === "percent" ? displayPercent(Number(v)) : String(v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-4 text-[12px] text-zinc-500 sm:px-6">
        Player numbers are TactiVision IDs, not shirt numbers.
      </p>
    </Card>
  );
}
