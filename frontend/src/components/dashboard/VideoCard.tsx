import { Tabs } from "radix-ui";
import { Clapperboard, VideoOff } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { getToken } from "../../api/client";
import { getMatchMedia } from "../../api/getMatchStats";
import { useTeamNames } from "../../lib/teamNames";
import { Card, CardHeader } from "../ui/Card";

type Kind = "match" | "analysis";

type KitColors = { team_a?: string; team_b?: string } | null | undefined;

export function VideoCard({ matchId, kitColors }: { matchId: string; kitColors?: KitColors }) {
  const [media, setMedia] = useState<{ source_video: boolean; analysis_video: boolean } | null>(null);
  const [kind, setKind] = useState<Kind>("match");
  const token = getToken();
  const auth = token ? `?token=${encodeURIComponent(token)}` : "";

  useEffect(() => {
    let stop = false;
    getMatchMedia(matchId)
      .then((m) => {
        if (stop) return;
        setMedia(m);
        if (!m.source_video && m.analysis_video) setKind("analysis");
      })
      .catch(() => !stop && setMedia({ source_video: false, analysis_video: false }));
    return () => {
      stop = true;
    };
  }, [matchId]);

  const src = kind === "analysis" ? `/api/matches/${matchId}/analysis-video${auth}` : `/api/matches/${matchId}/video${auth}`;
  const none = media && !media.source_video && !media.analysis_video;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader
        icon={<Clapperboard />}
        title="Match video"
        description={
          kind === "analysis" ? "Players, ball, goals and events as the analysis saw them." : "The footage you uploaded."
        }
        action={
          media?.analysis_video && media.source_video ? (
            <Tabs.Root value={kind} onValueChange={(v) => setKind(v as Kind)}>
              <Tabs.List className="flex rounded-lg bg-white/[0.05] p-0.5 text-[12px]" aria-label="Video source">
                {(
                  [
                    ["match", "Footage"],
                    ["analysis", "Tracking"],
                  ] as const
                ).map(([value, label]) => (
                  <Tabs.Trigger
                    key={value}
                    value={value}
                    className="cursor-pointer rounded-md px-3 py-1.5 text-zinc-400 transition-colors data-[state=active]:bg-white/10 data-[state=active]:text-white"
                  >
                    {label}
                  </Tabs.Trigger>
                ))}
              </Tabs.List>
            </Tabs.Root>
          ) : null
        }
      />
      <div className="flex-1 p-3 pt-4 sm:p-4">
        {media === null ? (
          <div className="skeleton aspect-video w-full rounded-xl" />
        ) : none ? (
          <div className="grid aspect-video w-full place-items-center rounded-xl border border-dashed border-white/10 bg-black/20 text-center">
            <div>
              <VideoOff className="mx-auto size-7 text-zinc-600" />
              <p className="mt-3 text-sm text-zinc-400">No video is stored for this match.</p>
            </div>
          </div>
        ) : (
          <video key={src} src={src} controls playsInline preload="metadata" className="aspect-video w-full rounded-xl bg-black" />
        )}
        {kind === "analysis" && !none ? <Legend kitColors={kitColors} /> : null}
      </div>
    </Card>
  );
}

function Legend({ kitColors }: { kitColors: KitColors }) {
  const names = useTeamNames();
  const ring = (color: string) => (
    <span className="inline-block h-2 w-3.5 rounded-[50%] border-2" style={{ borderColor: color }} />
  );
  const items: [ReactNode, string][] = [
    [ring(kitColors?.team_a ?? "var(--color-team-a)"), names.team_a],
    [ring(kitColors?.team_b ?? "var(--color-team-b)"), names.team_b],
    [ring("#f5d728"), "Referee"],
    [ring("#aaaaaa"), "Team unclear"],
    [<span className="inline-block size-2 rounded-full bg-white ring-2 ring-zinc-800" />, "Ball"],
    [<span className="inline-block border-x-[5px] border-t-[7px] border-x-transparent border-t-white" />, "On the ball"],
    [<span className="inline-block h-2.5 w-3.5 rounded-[2px] border border-white" />, "Goal"],
  ];
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-[12px] text-zinc-400" aria-label="Video legend">
      {items.map(([mark, label]) => (
        <li key={label} className="flex items-center gap-1.5">
          {mark}
          {label}
        </li>
      ))}
    </ul>
  );
}
