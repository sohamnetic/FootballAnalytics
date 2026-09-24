import { ArrowLeft, ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getMatchStats } from "../api/getMatchStats";
import { EventTiles } from "../components/dashboard/EventTiles";
import { DataNotes, TimelineCard } from "../components/dashboard/MatchNotes";
import { PlayersTable } from "../components/dashboard/PlayersTable";
import { PossessionCard } from "../components/dashboard/PossessionCard";
import { ScoreHero } from "../components/dashboard/ScoreHero";
import { TeamComparison } from "../components/dashboard/TeamComparison";
import { VideoCard } from "../components/dashboard/VideoCard";
import { PageShell } from "../components/layout/PageShell";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { TeamNamesContext } from "../lib/teamNames";
import type { MatchStats } from "../types/matchStats";

export function DashboardPage() {
  const { matchId } = useParams();
  const [stats, setStats] = useState<MatchStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!matchId) return;
    getMatchStats(matchId)
      .then(setStats)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "Failed to load match stats"));
  }, [matchId]);

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

  return (
    <TeamNamesContext.Provider value={names}>
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

        <div className="space-y-4">
          <ScoreHero stats={stats} />

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">{matchId ? <VideoCard matchId={matchId} kitColors={stats.match.kit_colors} /> : null}</div>
            <PossessionCard stats={stats} />
          </div>

          <EventTiles summary={stats.event_summary} />

          <div className="grid gap-4 lg:grid-cols-5">
            <div className="lg:col-span-2">
              <TeamComparison a={stats.teams.team_a} b={stats.teams.team_b} />
            </div>
            <div className="lg:col-span-3">
              <DataNotes stats={stats} />
            </div>
          </div>

          <PlayersTable players={stats.players} />

          <TimelineCard events={stats.events} />
        </div>
      </PageShell>
    </TeamNamesContext.Provider>
  );
}
