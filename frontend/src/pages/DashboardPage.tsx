import { ArrowLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getMatch, getMatchStats, savePlayerNames } from "../api/getMatchStats";
import { EventTiles } from "../components/dashboard/EventTiles";
import { DataNotes, TimelineCard } from "../components/dashboard/MatchNotes";
import { PlayerOfMatch } from "../components/dashboard/PlayerOfMatch";
import { PlayerPanel } from "../components/dashboard/PlayerPanel";
import { PlayersTable } from "../components/dashboard/PlayersTable";
import { PossessionCard } from "../components/dashboard/PossessionCard";
import { ScoreHero } from "../components/dashboard/ScoreHero";
import { TeamComparison } from "../components/dashboard/TeamComparison";
import { VideoCard } from "../components/dashboard/VideoCard";
import { PageShell } from "../components/layout/PageShell";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { PlayerNamesContext, type PlayerNames } from "../lib/playerNames";
import { cn } from "../lib/cn";
import { TeamNamesContext } from "../lib/teamNames";
import type { MatchStats, PlayerStats } from "../types/matchStats";

// on phones the dashboard is split into tabs instead of one very long page
type Tab = "summary" | "players" | "video";
const TABS: [Tab, string][] = [
  ["summary", "Summary"],
  ["players", "Players"],
  ["video", "Video"],
];

export function DashboardPage() {
  const { matchId } = useParams();
  const [tab, setTab] = useState<Tab>("summary");
  const [stats, setStats] = useState<MatchStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playerNames, setPlayerNames] = useState<PlayerNames>({});
  const [selected, setSelected] = useState<PlayerStats | null>(null);

  useEffect(() => {
    if (!matchId) return;
    getMatchStats(matchId)
      .then(setStats)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load match stats"));
    getMatch(matchId)
      .then((m) => setPlayerNames(m.player_names ?? {}))
      .catch(() => undefined);
  }, [matchId]);

  const saveName = useCallback(
    async (stableId: number, name: string) => {
      if (!matchId) return;
      setPlayerNames(await savePlayerNames(matchId, { [String(stableId)]: name }));
    },
    [matchId],
  );
  const namesValue = useMemo(() => ({ names: playerNames, save: matchId ? saveName : null }), [playerNames, matchId, saveName]);

  if (error) {
    return (
      <PageShell className="max-w-xl">
        <div className="pt-16">
          <Alert tone="error" title="We couldn't load this match">
            {error}
          </Alert>
          <Button asChild variant="secondary" className="mt-6">
            <Link to="/matches">
              <ArrowLeft /> Back to matches
            </Link>
          </Button>
        </div>
      </PageShell>
    );
  }

  if (!stats) {
    return (
      <PageShell>
        <div className="space-y-4 pt-10">
          <div className="skeleton h-4 w-40" />
          <div className="skeleton h-64 w-full rounded-3xl" />
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="skeleton h-80 rounded-2xl lg:col-span-2" />
            <div className="skeleton h-80 rounded-2xl" />
          </div>
        </div>
      </PageShell>
    );
  }

  const names = {
    team_a: stats.match.team_a_name || "Team A",
    team_b: stats.match.team_b_name || "Team B",
  };
  const best = stats.players.find((p) => p.stable_id === stats.player_of_the_match);
  // only the chosen tab on phones, everything from md up
  const on = (t: Tab, display: "block" | "grid" = "block") =>
    cn(tab !== t && (display === "grid" ? "hidden md:grid" : "hidden md:block"));

  return (
    <TeamNamesContext.Provider value={names}>
      <PlayerNamesContext.Provider value={namesValue}>
        <PageShell>
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 pt-8 pb-5 text-[13px] text-zinc-500">
            <Link to="/matches" className="hover:text-white">
              Matches
            </Link>
            <ChevronRight className="size-3.5" />
            <span className="truncate text-zinc-300">
              {names.team_a} vs {names.team_b}
            </span>
          </nav>

          <div
            role="tablist"
            aria-label="Dashboard sections"
            className="sticky top-[calc(4rem+env(safe-area-inset-top))] z-30 -mx-4 mb-4 flex gap-1 bg-ink-950/85 px-4 py-2 backdrop-blur-xl md:hidden"
          >
            {TABS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => {
                  setTab(id);
                  window.scrollTo({ top: 0 });
                }}
                className={cn(
                  "flex-1 cursor-pointer rounded-lg py-2 text-[13px] font-medium transition-colors",
                  tab === id ? "bg-white/10 text-white" : "text-zinc-400 active:text-white",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="space-y-4">
            <div className={on("summary")}>
              <ScoreHero stats={stats} />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className={cn("lg:col-span-2", on("video"))}>
                {matchId ? <VideoCard matchId={matchId} kitColors={stats.match.kit_colors} /> : null}
              </div>
              <div className={on("summary")}>
                <PossessionCard stats={stats} />
              </div>
            </div>

            <div className={on("summary")}>
              <EventTiles summary={stats.event_summary} />
            </div>

            <div className={cn("grid gap-4 lg:grid-cols-5", on("summary", "grid"))}>
              <div className="lg:col-span-2">
                <TeamComparison a={stats.teams.team_a} b={stats.teams.team_b} />
              </div>
              <div className="flex flex-col gap-4 lg:col-span-3">
                {best ? <PlayerOfMatch player={best} onSelect={setSelected} /> : null}
                <DataNotes stats={stats} />
              </div>
            </div>

            <div className={on("players")}>
              <PlayersTable players={stats.players} onSelect={setSelected} />
            </div>

            <div className={on("summary")}>
              <TimelineCard events={stats.events} />
            </div>
          </div>
          <PlayerPanel player={selected} onClose={() => setSelected(null)} />
        </PageShell>
      </PlayerNamesContext.Provider>
    </TeamNamesContext.Provider>
  );
}
