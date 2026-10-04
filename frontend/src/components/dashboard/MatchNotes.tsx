import { ListChecks, Waypoints } from "lucide-react";
import { playerLabel } from "../../lib/format";
import { usePlayerNames } from "../../lib/playerNames";
import { teamLabel, useTeamNames } from "../../lib/teamNames";
import type { MatchStats, TimelineEvent } from "../../types/matchStats";
import { Card, CardBody, CardHeader } from "../ui/Card";

export function TimelineCard({ events }: { events?: TimelineEvent[] }) {
  const names = useTeamNames();
  const { names: playerNames } = usePlayerNames();
  const has = Array.isArray(events) && events.length > 0;
  return (
    <Card className="h-full">
      <CardHeader icon={<Waypoints />} title="Timeline" description="Key moments in order." />
      <CardBody>
        {has ? (
          <ol className="relative space-y-4 border-l border-white/10 pl-5">
            {events!.map((e, i) => (
              <li key={`${e.type}-${i}`} className="relative text-sm">
                <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full bg-pitch-400 ring-4 ring-ink-900" />
                <span className="font-mono text-[12px] text-zinc-500 tabular">{e.time_s ?? "–"}s</span>
                <p className="text-white">
                  {e.type.toLowerCase()} · {e.team_id ? teamLabel(e.team_id, names) : "–"}
                  {e.stable_id !== null && e.stable_id !== undefined ? ` · ${playerLabel(e.stable_id, playerNames)}` : ""}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <div className="rounded-xl border border-dashed border-white/10 px-5 py-10 text-center">
            <p className="text-sm text-zinc-300">A minute-by-minute timeline is coming soon.</p>
            <p className="mt-1 text-[13px] text-zinc-500">For now, the totals above cover every event we detected.</p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function DataNotes({ stats }: { stats: MatchStats }) {
  const q = stats.data_quality;
  const facts: [string, string][] = [
    ["Players identified", String(q.stable_ids)],
    ["Players with a team", q.valid_team_players !== undefined ? String(q.valid_team_players) : "–"],
    ["Confirmed possession", q.possession_confirmed_seconds !== undefined ? `${q.possession_confirmed_seconds.toFixed(1)}s` : "–"],
    ["Pipeline", stats.pipeline_version ?? "–"],
  ];
  return (
    <Card className="flex-1">
      <CardHeader icon={<ListChecks />} title="About these numbers" description="How much of the match we could read." />
      <CardBody>
        <dl className="grid grid-cols-2 gap-3">
          {facts.map(([k, v]) => (
            <div key={k} className="rounded-xl bg-white/[0.03] p-3">
              <dt className="text-[12px] text-zinc-500">{k}</dt>
              <dd className="mt-1 truncate font-mono text-sm text-white tabular">{v}</dd>
            </div>
          ))}
        </dl>
      </CardBody>
    </Card>
  );
}
