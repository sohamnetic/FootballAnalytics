import { Accordion } from "radix-ui";
import { ChevronDown, ListChecks, Waypoints } from "lucide-react";
import { playerLabel } from "../../lib/format";
import { teamLabel, useTeamNames } from "../../lib/teamNames";
import type { MatchStats, TimelineEvent } from "../../types/matchStats";
import { Card, CardBody, CardHeader } from "../ui/Card";

export function TimelineCard({ events }: { events?: TimelineEvent[] }) {
  const names = useTeamNames();
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
                  {e.stable_id !== null && e.stable_id !== undefined ? ` · ${playerLabel(e.stable_id)}` : ""}
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
  const notes = stats.known_limitations ?? [];

  return (
    <Card className="h-full">
      <CardHeader icon={<ListChecks />} title="About these numbers" description="What the footage can and can't tell us." />
      <CardBody>
        <dl className="grid grid-cols-2 gap-3">
          {facts.map(([k, v]) => (
            <div key={k} className="rounded-xl bg-white/[0.03] p-3">
              <dt className="text-[12px] text-zinc-500">{k}</dt>
              <dd className="mt-1 truncate font-mono text-sm text-white tabular">{v}</dd>
            </div>
          ))}
        </dl>
        {notes.length ? (
          <Accordion.Root type="single" collapsible defaultValue="notes" className="mt-4">
            <Accordion.Item value="notes" className="rounded-xl border border-white/[0.06]">
              <Accordion.Header>
                <Accordion.Trigger className="group flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left text-sm text-zinc-300 hover:text-white">
                  Method notes ({notes.length})
                  <ChevronDown className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Content className="overflow-hidden">
                <ul className="space-y-2.5 px-4 pb-4 text-[13px] leading-relaxed text-zinc-400">
                  {notes.map((n) => (
                    <li key={n} className="flex gap-2.5">
                      <span className="mt-2 size-1 shrink-0 rounded-full bg-zinc-600" />
                      {n}
                    </li>
                  ))}
                </ul>
              </Accordion.Content>
            </Accordion.Item>
          </Accordion.Root>
        ) : null}
      </CardBody>
    </Card>
  );
}
